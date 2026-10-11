from __future__ import annotations

import json
import threading

from PyQt6.QtCore import QThread, pyqtSignal

from .ai import GeminiService
from .security import redact_sensitive_text
from .tools.registry import ApprovalRequired
from .tools.builtins import ToolExecutor


class TaskAgentWorker(QThread):
    plan_ready = pyqtSignal(list)
    progress = pyqtSignal(int, str)
    approval_needed = pyqtSignal(str)
    completed = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, goal: str, ai: GeminiService, executor: ToolExecutor, parent=None) -> None:
        super().__init__(parent)
        self.goal = goal.strip()
        self.ai = ai
        self.executor = executor
        self._cancel = threading.Event()
        self._pause = threading.Event()
        self._pause.set()
        self._approval = threading.Event()
        self._approved = False

    def pause(self) -> None:
        self._pause.clear()

    def resume(self) -> None:
        self._pause.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._pause.set()
        self._approved = False
        self._approval.set()

    def answer_approval(self, approved: bool) -> None:
        self._approved = approved
        self._approval.set()

    def _wait_ready(self) -> bool:
        while not self._cancel.is_set():
            if self._pause.wait(0.1):
                return True
        return False

    def run(self) -> None:
        try:
            tool_index = self.executor.registry
            visible_tools = []
            for spec in tool_index.all():
                visible_tools.append({
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {key: {"type": kind.__name__, "required": required} for key, (kind, required) in spec.parameters.items()},
                    "requires_confirmation": spec.requires_confirmation,
                })
            plan = self.ai.plan_task(self.goal, visible_tools)
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            validated = []
            for item in plan:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("tool", ""))
                args = item.get("arguments", {})
                label = str(item.get("label", name.replace("_", " ").title()))[:180]
                spec = self.executor.registry.get(name)
                if spec is None:
                    continue
                ToolExecutor._validate(spec, args)
                validated.append({"tool": name, "arguments": args, "label": label})
            if not validated:
                raise RuntimeError("No supported actions fit that request. You can use the chat or Research panel instead.")
            self.plan_ready.emit(validated)
            sources = []
            document_result = None
            summaries = []
            for index, step in enumerate(validated, start=1):
                if not self._wait_ready():
                    self.cancelled.emit()
                    return
                label = step["label"]
                self.progress.emit(index, f"{label}…")
                self._approval.clear()
                try:
                    result = self.executor.execute(step["tool"], step["arguments"])
                except ApprovalRequired as request:
                    self.approval_needed.emit(request.summary)
                    while not self._cancel.is_set() and not self._approval.wait(0.1):
                        pass
                    if self._cancel.is_set():
                        self.cancelled.emit()
                        return
                    if not self._approved:
                        self.progress.emit(index, f"Skipped after approval was declined: {label}")
                        continue
                    result = self.executor.execute(step["tool"], step["arguments"], approved=True)
                if self._cancel.is_set():
                    self.cancelled.emit()
                    return
                summaries.append(f"{label}: {json.dumps(result, ensure_ascii=False, default=str)[:5000]}")
                if step["tool"] == "web_search" and isinstance(result, list):
                    sources = result
                if step["tool"] == "file_read" and isinstance(result, dict) and result.get("text"):
                    document_result = result
                self.progress.emit(index, f"Completed: {label}")
            if self._cancel.is_set():
                self.cancelled.emit()
                return
            reports = []
            if sources and not self._cancel.is_set():
                self.progress.emit(len(validated) + 1, "Preparing a source-linked research summary…")
                summary = self.ai.summarize_research(self.goal, sources)
                if self._cancel.is_set():
                    self.cancelled.emit()
                    return
                reports.append(summary + "\n\nSources:\n" + "\n".join(
                    f"[{i}] {source.get('title', 'Source')} — {source.get('url', '')}" for i, source in enumerate(sources, start=1)
                ))
            else:
                reports.append("Task finished.\n\n" + "\n".join(summaries))
            if document_result and not self._cancel.is_set():
                self.progress.emit(len(validated) + 1, "Summarizing the approved document with Gemini…")
                report = self.ai.summarize_document(
                    self.goal, document_result.get("path", "approved document"), document_result["text"]
                )
                if self._cancel.is_set():
                    self.cancelled.emit()
                    return
                reports.append("Document summary:\n" + report)
            rendered = "\n\n".join(reports)
            self.completed.emit(rendered)
        except Exception as exc:
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(redact_sensitive_text(str(exc)))

