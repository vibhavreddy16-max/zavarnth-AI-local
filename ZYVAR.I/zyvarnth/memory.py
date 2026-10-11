from __future__ import annotations

import re
from typing import Any

from .database import Database, utc_now


class MemoryStore:
    """User-approved long-term facts, kept separate from conversation transcripts."""

    def __init__(self, database: Database) -> None:
        self.db = database

    def save(self, category: str, key: str, value: str) -> int:
        category, key, value = category.strip(), key.strip(), value.strip()
        if not category or not key or not value:
            raise ValueError("Category, fact name, and fact value are required.")
        if len(key) > 120 or len(value) > 4000:
            raise ValueError("Memory entry is too long.")
        now = utc_now()
        with self.db.connect() as conn:
            found = conn.execute("SELECT id FROM memories WHERE fact_key=?", (key,)).fetchone()
            if found:
                conn.execute(
                    "UPDATE memories SET category=?,fact_value=?,updated_at=? WHERE id=?",
                    (category, value, now, found["id"]),
                )
                return int(found["id"])
            cursor = conn.execute(
                "INSERT INTO memories(category,fact_key,fact_value,created_at,updated_at) "
                "VALUES(?,?,?,?,?)",
                (category, key, value, now, now),
            )
            return int(cursor.lastrowid)

    def list(self, query: str = "") -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM memories WHERE fact_key LIKE ? OR fact_value LIKE ? "
                "OR category LIKE ? ORDER BY updated_at DESC",
                (f"%{query}%", f"%{query}%", f"%{query}%"),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete(self, memory_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))

    def erase_all(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memories")

    def recall(self, query: str, limit: int = 8) -> list[dict[str, Any]]:
        tokens = {token.lower() for token in re.findall(r"[\w'-]{2,}", query)}
        entries = self.list()
        ranked: list[tuple[int, dict[str, Any]]] = []
        for item in entries:
            haystack = f"{item['category']} {item['fact_key']} {item['fact_value']}".lower()
            score = sum(1 for token in tokens if token in haystack)
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (pair[0], pair[1]["updated_at"]), reverse=True)
        return [item for _, item in ranked[:limit]]

