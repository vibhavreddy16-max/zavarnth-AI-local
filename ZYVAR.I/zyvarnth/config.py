from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

APP_NAME = "Zyvarnth"
CONFIG_DIR = Path(user_config_dir(APP_NAME, appauthor=False))
DATA_DIR = Path(user_data_dir(APP_NAME, appauthor=False))
CONFIG_FILE = CONFIG_DIR / "settings.json"
DATABASE_FILE = DATA_DIR / "zyvarnth.sqlite3"
KEYRING_SERVICE = "zyvarnth"

DEFAULT_SETTINGS: dict[str, Any] = {
    "text_model": os.getenv("GEMINI_TEXT_MODEL", "gemini-3.8-flash"),
    "live_model": os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live"),
    "voice": "Aoede",
    "memory_enabled": True,
    "approved_roots": [],
    "input_device": None,
    "output_device": None,
    "theme": "cyan",
    "compact_mode": False,
    "enabled_plugins": [],
}


class Settings:
    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._values = dict(DEFAULT_SETTINGS)
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                self._values.update(saved)
        except (OSError, json.JSONDecodeError):
            pass

    def get(self, name: str, default: Any = None) -> Any:
        return self._values.get(name, default)

    def set(self, name: str, value: Any) -> None:
        self._values[name] = value
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._values, indent=2), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(self.path)


def get_api_key() -> str | None:
    """Get a key from the OS keychain, then the explicitly supported env fallback."""
    try:
        import keyring

        value = keyring.get_password(KEYRING_SERVICE, "google-gemini")
        if value:
            return value
    except Exception:
        pass
    return os.getenv("GEMINI_API_KEY") or None


def save_api_key(value: str) -> None:
    key = value.strip()
    if not key:
        raise ValueError("Enter a non-empty API key.")
    try:
        import keyring

        keyring.set_password(KEYRING_SERVICE, "google-gemini", key)
    except Exception as exc:
        raise RuntimeError("The system credential store is unavailable; the key was not saved.") from exc


def delete_api_key() -> None:
    try:
        import keyring
        if keyring.get_password(KEYRING_SERVICE, "google-gemini"):
            keyring.delete_password(KEYRING_SERVICE, "google-gemini")
    except Exception as exc:
        raise RuntimeError("The saved key could not be removed from the system credential store.") from exc

