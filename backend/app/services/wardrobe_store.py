"""Durable, metadata-only wardrobe storage for the local Aura gateway."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.user import UserProfile, WardrobeItem


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_database_url(value: str | None) -> Path:
    raw = (value or "").strip()
    if raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///"):]
    elif raw.startswith("sqlite://"):
        raw = raw[len("sqlite://"):]
    path = Path(raw) if raw else Path(__file__).resolve().parents[2] / "data" / "aura.sqlite3"
    return path.expanduser() if path.is_absolute() else (Path.cwd() / path).resolve()


class WardrobeStore:
    def __init__(self, database_url: str | None = None):
        self.path = _parse_database_url(database_url or os.getenv("AURA_DATABASE_URL"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS wardrobe_items (
                    user_id TEXT NOT NULL,
                    item_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    category TEXT,
                    subtype TEXT,
                    subcategory TEXT,
                    color TEXT,
                    material TEXT,
                    style TEXT,
                    confidence REAL,
                    source TEXT NOT NULL DEFAULT 'wardrobe',
                    memory_status TEXT NOT NULL CHECK(memory_status IN ('temporary', 'remembered')),
                    colors_json TEXT NOT NULL DEFAULT '[]',
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    expires_at TEXT,
                    updated_at TEXT NOT NULL
                )
            """)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_wardrobe_user ON wardrobe_items(user_id)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_wardrobe_expiry ON wardrobe_items(expires_at)")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS user_profiles (
                    user_id TEXT PRIMARY KEY,
                    profile_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

    @staticmethod
    def _row_to_item(row: sqlite3.Row) -> WardrobeItem:
        import json
        return WardrobeItem(
            id=row["item_id"], name=row["name"], category=row["category"],
            subtype=row["subtype"], subcategory=row["subcategory"], color=row["color"],
            material=row["material"] or "unknown", style=row["style"] or "casual",
            confidence=row["confidence"], image_url=None, source=row["source"],
            memory_type=row["memory_status"], expires_at=row["expires_at"],
            colors=json.loads(row["colors_json"] or "[]"), tags=json.loads(row["tags_json"] or "[]"),
        )

    def _delete_expired(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM wardrobe_items WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (_utc_now().isoformat(),),
        )

    def list(self, user_id: str) -> list[WardrobeItem]:
        with self._connect() as connection:
            self._delete_expired(connection)
            rows = connection.execute(
                "SELECT * FROM wardrobe_items WHERE user_id = ? ORDER BY created_at ASC",
                (user_id,),
            ).fetchall()
        return [self._row_to_item(row) for row in rows]

    def create(self, user_id: str, item: WardrobeItem) -> WardrobeItem:
        import json
        now = _utc_now()
        item_id = item.id or __import__("uuid").uuid4().hex
        expiry = now + __import__("datetime").timedelta(days=30) if item.memory_type == "temporary" else None
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO wardrobe_items
                (user_id, item_id, name, category, subtype, subcategory, color, material, style,
                 confidence, source, memory_status, colors_json, tags_json, created_at, expires_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user_id, item_id, item.name, item.category, item.subtype, item.subcategory,
                 item.color, item.material, item.style, item.confidence, "wardrobe", item.memory_type,
                 json.dumps(item.colors), json.dumps(item.tags), now.isoformat(), expiry.isoformat() if expiry else None, now.isoformat()),
            )
        item.id = item_id
        item.source = "wardrobe"
        item.expires_at = expiry
        return item

    def update(self, user_id: str, item_id: str, item: WardrobeItem) -> WardrobeItem | None:
        import json
        now = _utc_now()
        expiry = now + __import__("datetime").timedelta(days=30) if item.memory_type == "temporary" else None
        with self._connect() as connection:
            result = connection.execute(
                """UPDATE wardrobe_items SET name=?, category=?, subtype=?, subcategory=?, color=?, material=?,
                style=?, confidence=?, source='wardrobe', memory_status=?, colors_json=?, tags_json=?,
                expires_at=?, updated_at=? WHERE user_id=? AND item_id=?""",
                (item.name, item.category, item.subtype, item.subcategory, item.color, item.material,
                 item.style, item.confidence, item.memory_type, json.dumps(item.colors), json.dumps(item.tags),
                 expiry.isoformat() if expiry else None, now.isoformat(), user_id, item_id),
            )
        if result.rowcount == 0:
            return None
        item.id = item_id
        item.source = "wardrobe"
        item.expires_at = expiry
        return item

    def delete(self, user_id: str, item_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM wardrobe_items WHERE user_id=? AND item_id=?", (user_id, item_id))
        return result.rowcount > 0

    def clear(self, user_id: str) -> int:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM wardrobe_items WHERE user_id=?", (user_id,))
        return result.rowcount

    def get_profile(self, user_id: str) -> UserProfile:
        import json
        with self._connect() as connection:
            row = connection.execute("SELECT profile_json FROM user_profiles WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return UserProfile()
        try:
            return UserProfile.model_validate(json.loads(row["profile_json"]))
        except (ValueError, TypeError):
            return UserProfile()

    def save_profile(self, user_id: str, profile: UserProfile) -> UserProfile:
        import json
        now = _utc_now().isoformat()
        payload = json.dumps(profile.model_dump(mode="json"), sort_keys=True)
        with self._connect() as connection:
            connection.execute("""
                INSERT INTO user_profiles(user_id, profile_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json, updated_at=excluded.updated_at
            """, (user_id, payload, now, now))
        return profile

    def delete_profile(self, user_id: str) -> bool:
        with self._connect() as connection:
            result = connection.execute("DELETE FROM user_profiles WHERE user_id=?", (user_id,))
        return result.rowcount > 0


def create_store(database_url: str | None = None) -> WardrobeStore:
    return WardrobeStore(database_url)
