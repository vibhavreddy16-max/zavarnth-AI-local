from __future__ import annotations

import json
import os
import stat
import threading
from io import BytesIO

import pytest

from zyvarnth.config import Settings
from zyvarnth.ai import GeminiService
from zyvarnth.database import Database
from zyvarnth.memory import MemoryStore
from zyvarnth.plugins import PluginManager
from zyvarnth.security import SecurityError, safe_pattern, validate_http_url
from zyvarnth.tools.builtins import ToolExecutor
from zyvarnth.tools.registry import ApprovalRequired


@pytest.fixture
def environment(tmp_path):
    settings = Settings(tmp_path / "settings.json")
    approved = tmp_path / "approved"
    approved.mkdir()
    settings.set("approved_roots", [str(approved)])
    database = Database(tmp_path / "zyvarnth.sqlite3")
    return settings, database, approved, ToolExecutor(settings, database)


def test_conversation_and_memories_are_separate(environment):
    _, database, _, _ = environment
    memory = MemoryStore(database)
    session = database.create_session("Research")
    database.append_message(session, "user", "I prefer concise reports.")
    memory.save("Preference", "report_style", "Concise reports with source links")

    assert database.messages(session)[0]["content"] == "I prefer concise reports."
    assert memory.recall("How should reports look?")[0]["fact_key"] == "report_style"
    assert database.messages(session)[0]["role"] == "user"


def test_conversation_retrieves_relevant_older_messages(environment):
    _, database, _, _ = environment
    session = database.create_session("Long conversation")
    database.append_message(session, "user", "Project Orion budget is 42 thousand dollars.")
    database.append_message(session, "assistant", "I will keep the Orion budget context for this discussion.")
    for number in range(14):
        database.append_message(session, "user", f"Unrelated recent turn {number}.")
        database.append_message(session, "assistant", f"Unrelated answer {number}.")

    recalled = database.relevant_messages(session, "What was the Orion budget?", limit=3)
    assert any("42 thousand" in item["content"] for item in recalled)


def test_gemini_does_not_fake_a_reply_when_unconfigured(environment, monkeypatch):
    settings, database, _, _ = environment
    monkeypatch.setattr("zyvarnth.ai.get_api_key", lambda: None)
    service = GeminiService(settings, MemoryStore(database))
    streamed = []

    with pytest.raises(RuntimeError, match="Add an API key"):
        service.stream_reply(
            [{"role": "user", "content": "hello"}],
            on_text=streamed.append,
            cancel=threading.Event(),
        )
    assert streamed == []


def test_file_write_requires_approval_and_can_be_undone(environment):
    _, database, approved, tools = environment
    target = approved / "notes.txt"
    target.write_text("original", encoding="utf-8")
    arguments = {"path": str(target), "content": "updated"}

    with pytest.raises(ApprovalRequired):
        tools.execute("file_write", arguments)
    assert target.read_text(encoding="utf-8") == "original"

    payload = tools.execute("file_write", arguments, approved=True)
    assert target.read_text(encoding="utf-8") == "updated"
    action = database.actions(1)[0]
    assert action["payload"] == payload
    assert tools.undo(action["id"]).startswith("Undid")
    assert target.read_text(encoding="utf-8") == "original"
    assert database.actions(1)[0]["undone"] == 1


def test_undo_does_not_overwrite_later_file_changes(environment):
    _, database, approved, tools = environment
    target = approved / "notes.txt"
    target.write_text("first", encoding="utf-8")
    tools.execute("file_write", {"path": str(target), "content": "assistant edit"}, approved=True)
    action_id = database.actions(1)[0]["id"]
    target.write_text("user edit after", encoding="utf-8")

    with pytest.raises(RuntimeError, match="changed after"):
        tools.undo(action_id)
    assert target.read_text(encoding="utf-8") == "user edit after"


def test_undo_detects_replacement_even_when_contents_match(environment):
    _, database, approved, tools = environment
    target = approved / "notes.txt"
    tools.execute("file_write", {"path": str(target), "content": "assistant output"}, approved=True)
    action_id = database.actions(1)[0]["id"]
    replacement = approved / "replacement.txt"
    replacement.write_text("assistant output", encoding="utf-8")
    os.replace(replacement, target)

    with pytest.raises(RuntimeError, match="changed after"):
        tools.undo(action_id)


def test_undo_restores_original_mode(environment):
    _, database, approved, tools = environment
    target = approved / "notes.txt"
    target.write_text("original", encoding="utf-8")
    target.chmod(0o640)
    original_mode = stat.S_IMODE(target.stat().st_mode)
    tools.execute("file_write", {"path": str(target), "content": "updated"}, approved=True)
    action_id = database.actions(1)[0]["id"]
    tools.undo(action_id)
    assert stat.S_IMODE(target.stat().st_mode) == original_mode
    assert target.read_text(encoding="utf-8") == "original"


def test_volume_is_reversible_only_when_readback_confirms_the_change(environment, monkeypatch):
    _, database, _, tools = environment

    class VolumeAdapter:
        value = 30

        def read_volume(self):
            return self.value

        def set_volume(self, percent):
            # Simulate an OS API that accepts the call but leaves the setting unchanged.
            return None

    adapter = VolumeAdapter()
    monkeypatch.setattr("zyvarnth.tools.builtins.SystemSettingsAdapter", lambda: adapter)
    result = tools.execute("set_volume", {"percent": 70})

    action = database.actions(1)[0]
    assert result == {"before": 30, "after": 30}
    assert action["reversible"] == 0
    assert action["payload"] == {}


def test_volume_undo_refuses_to_overwrite_a_later_setting_change(environment, monkeypatch):
    _, database, _, tools = environment

    class VolumeAdapter:
        value = 30

        def read_volume(self):
            return self.value

        def set_volume(self, percent):
            self.value = percent

    adapter = VolumeAdapter()
    monkeypatch.setattr("zyvarnth.tools.builtins.SystemSettingsAdapter", lambda: adapter)
    tools.execute("set_volume", {"percent": 70})
    action_id = database.actions(1)[0]["id"]
    assert database.actions(1)[0]["reversible"] == 1

    adapter.value = 80
    with pytest.raises(RuntimeError, match="Volume changed after"):
        tools.undo(action_id)
    assert adapter.value == 80


def test_file_access_stays_inside_approved_roots(environment, tmp_path):
    _, _, _, tools = environment
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    with pytest.raises(SecurityError, match="outside"):
        tools.execute("file_read", {"path": str(outside)})


def test_unknown_tools_are_rejected(environment):
    _, _, _, tools = environment
    with pytest.raises(PermissionError, match="Unknown or unauthorized"):
        tools.execute("shell", {"command": "whoami"})


def test_browser_interaction_requires_human_approval(environment):
    _, _, _, tools = environment
    with pytest.raises(ApprovalRequired, match="may submit a form"):
        tools.execute(
            "browser_interact",
            {"url": "https://example.com", "action": "click", "selector": "button.submit"},
        )


def test_disabled_plugins_are_not_imported(environment, tmp_path):
    settings, _, _, tools = environment
    plugin_dir = tmp_path / "plugins"
    plugin_dir.mkdir()
    marker = tmp_path / "plugin-imported"
    (plugin_dir / "sample.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('loaded')\n"
        "from zyvarnth.tools.registry import ToolSpec\n"
        "def ping(): return {'ok': True}\n"
        "def register(): return [ToolSpec('plugin_ping','Check plugin loading',{},ping)]\n",
        encoding="utf-8",
    )
    manager = PluginManager(settings, tools.registry, plugin_dir)

    assert manager.load_enabled() == []
    assert not marker.exists()
    settings.set("enabled_plugins", ["sample"])
    assert manager.load_enabled() == [("sample", "loaded")]
    assert marker.read_text(encoding="utf-8") == "loaded"
    assert tools.execute("plugin_ping", {}) == {"ok": True}


def test_browser_urls_and_file_patterns_are_validated():
    assert validate_http_url("https://example.com/path") == "https://example.com/path"
    with pytest.raises(SecurityError):
        validate_http_url("file:///etc/passwd")
    with pytest.raises(SecurityError):
        validate_http_url("https://user:password@example.com/")
    assert safe_pattern("*.pdf") == "*.pdf"
    with pytest.raises(SecurityError):
        safe_pattern("../*.pdf")


def test_actions_are_logged_without_persisting_file_contents(environment):
    _, database, approved, tools = environment
    target = approved / "secret.txt"
    tools.execute("file_write", {"path": str(target), "content": "TOP SECRET CONTENT"}, approved=True)
    action = database.actions(1)[0]
    serialized = json.dumps(action)
    assert "TOP SECRET CONTENT" not in serialized
    assert action["reversible"] == 1


def test_word_document_extraction_stays_within_approved_roots(environment):
    from docx import Document

    _, _, approved, tools = environment
    buffer = BytesIO()
    document = Document()
    document.add_paragraph("A locally approved project note.")
    document.save(buffer)
    target = approved / "brief.docx"
    target.write_bytes(buffer.getvalue())

    result = tools.execute("file_read", {"path": str(target)})
    assert "locally approved project note" in result["text"]

