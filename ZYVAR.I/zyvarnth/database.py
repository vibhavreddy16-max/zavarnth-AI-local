from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .config import DATABASE_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Small SQLite store. Each operation owns a connection for thread safety."""

    def __init__(self, path: Path = DATABASE_FILE) -> None:
        self.path = path
        self._init_lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self._init_lock, self.connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK(role IN ('user','assistant','tool')),
                    content TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session ON messages(session_id, id);
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT NOT NULL,
                    fact_key TEXT NOT NULL, fact_value TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS memories_key ON memories(fact_key);
                CREATE TABLE IF NOT EXISTS actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, tool_name TEXT NOT NULL,
                    summary TEXT NOT NULL, payload TEXT NOT NULL,
                    reversible INTEGER NOT NULL DEFAULT 0, undone INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, undone_at TEXT
                );
                CREATE TABLE IF NOT EXISTS reminders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                    due_at TEXT NOT NULL, fired INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_session(self, title: str = "New conversation") -> str:
        session_id = str(uuid.uuid4())
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO sessions(id,title,created_at,updated_at) VALUES(?,?,?,?)",
                (session_id, title[:120], now, now),
            )
        return session_id

    def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT id,title,created_at,updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def messages(self, session_id: str, limit: int = 60) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT role,content,created_at FROM messages WHERE session_id=? "
                "ORDER BY id DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def relevant_messages(self, session_id: str, query: str, limit: int = 6) -> list[dict[str, Any]]:
        ignored = {"what", "when", "where", "that", "this", "with", "from", "have", "about", "does", "did", "would", "could", "should", "please", "tell", "show", "help"}
        tokens = {word.lower() for word in re.findall(r"[\w'-]{3,}", query) if word.lower() not in ignored}
        if not tokens:
            return []
        with self.connect() as db:
            rows = db.execute(
                "SELECT role,content,created_at FROM messages WHERE session_id=? ORDER BY id",
                (session_id,),
            ).fetchall()
        ranked = []
        for row in rows:
            item = dict(row)
            score = sum(token in item["content"].lower() for token in tokens)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (pair[0], pair[1]["created_at"]), reverse=True)
        return sorted([item for _, item in ranked[:limit]], key=lambda item: item["created_at"])

    def append_message(self, session_id: str, role: str, content: str) -> None:
        if role not in {"user", "assistant", "tool"}:
            raise ValueError("Unknown message role.")
        now = utc_now()
        with self.connect() as db:
            db.execute(
                "INSERT INTO messages(session_id,role,content,created_at) VALUES(?,?,?,?)",
                (session_id, role, content, now),
            )
            title = db.execute("SELECT title FROM sessions WHERE id=?", (session_id,)).fetchone()
            if role == "user" and title and title["title"] in {"Conversation", "New conversation"}:
                title_text = " ".join(content.split())[:60] or "Conversation"
                db.execute(
                    "UPDATE sessions SET title=?,updated_at=? WHERE id=?",
                    (title_text, now, session_id),
                )
            else:
                db.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))

    def add_action(
        self, tool_name: str, summary: str, payload: dict[str, Any], reversible: bool
    ) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO actions(tool_name,summary,payload,reversible,created_at) "
                "VALUES(?,?,?,?,?)",
                (tool_name, summary, json.dumps(payload), int(reversible), utc_now()),
            )
            return int(cursor.lastrowid)

    def actions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute("SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            result.append(item)
        return result

    def mark_undone(self, action_id: int) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE actions SET undone=1,undone_at=? WHERE id=?",
                (utc_now(), action_id),
            )

    def add_reminder(self, title: str, due_at: str) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO reminders(title,due_at,created_at) VALUES(?,?,?)",
                (title, due_at, utc_now()),
            )
            return int(cursor.lastrowid)

    def due_reminders(self, now: str) -> list[dict[str, Any]]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM reminders WHERE fired=0 AND due_at<=? ORDER BY due_at", (now,)
            ).fetchall()
            db.executemany("UPDATE reminders SET fired=1 WHERE id=?", [(row["id"],) for row in rows])
        return [dict(row) for row in rows]

