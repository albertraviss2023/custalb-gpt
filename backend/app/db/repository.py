from __future__ import annotations

import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from app.models.schemas import ChatDetail, ChatSummary, MessageRecord


class Repository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.lock = threading.Lock()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _as_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    def get_default_model_id(self, fallback: str) -> str:
        row = self.connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("default_model_id",),
        ).fetchone()
        if row:
            return str(row["value"])
        return fallback

    def set_default_model_id(self, model_id: str) -> None:
        now = self._now_iso()
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO settings(key, value, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                ("default_model_id", model_id, now),
            )
            self.connection.commit()

    def create_chat(self, title: str, selected_model_id: str | None) -> ChatSummary:
        now = self._now_iso()
        chat_id = str(uuid.uuid4())
        with self.lock:
            self.connection.execute(
                "INSERT INTO chats(id, title, selected_model_id, created_at, updated_at) VALUES(?, ?, ?, ?, ?)",
                (chat_id, title, selected_model_id, now, now),
            )
            self.connection.commit()

        return ChatSummary(
            id=chat_id,
            title=title,
            selected_model_id=selected_model_id,
            created_at=self._as_datetime(now),
            updated_at=self._as_datetime(now),
        )

    def list_chats(self) -> list[ChatSummary]:
        rows = self.connection.execute(
            "SELECT id, title, selected_model_id, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        return [
            ChatSummary(
                id=str(row["id"]),
                title=str(row["title"]),
                selected_model_id=row["selected_model_id"],
                created_at=self._as_datetime(str(row["created_at"])),
                updated_at=self._as_datetime(str(row["updated_at"])),
            )
            for row in rows
        ]

    def get_chat(self, chat_id: str) -> ChatDetail | None:
        chat_row = self.connection.execute(
            "SELECT id, title, selected_model_id, created_at, updated_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if not chat_row:
            return None

        message_rows = self.connection.execute(
            """
            SELECT id, chat_id, role, content, model_id, created_at
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
            """,
            (chat_id,),
        ).fetchall()

        messages = [
            MessageRecord(
                id=str(row["id"]),
                chat_id=str(row["chat_id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                model_id=row["model_id"],
                created_at=self._as_datetime(str(row["created_at"])),
            )
            for row in message_rows
        ]

        return ChatDetail(
            id=str(chat_row["id"]),
            title=str(chat_row["title"]),
            selected_model_id=chat_row["selected_model_id"],
            created_at=self._as_datetime(str(chat_row["created_at"])),
            updated_at=self._as_datetime(str(chat_row["updated_at"])),
            messages=messages,
        )

    def update_chat(self, chat_id: str, title: str | None, selected_model_id: str | None) -> ChatSummary | None:
        current = self.connection.execute(
            "SELECT id, title, selected_model_id, created_at, updated_at FROM chats WHERE id = ?",
            (chat_id,),
        ).fetchone()
        if not current:
            return None

        new_title = title if title is not None else str(current["title"])
        new_model_id = selected_model_id if selected_model_id is not None else current["selected_model_id"]
        now = self._now_iso()

        with self.lock:
            self.connection.execute(
                "UPDATE chats SET title = ?, selected_model_id = ?, updated_at = ? WHERE id = ?",
                (new_title, new_model_id, now, chat_id),
            )
            self.connection.commit()

        return ChatSummary(
            id=chat_id,
            title=new_title,
            selected_model_id=new_model_id,
            created_at=self._as_datetime(str(current["created_at"])),
            updated_at=self._as_datetime(now),
        )

    def delete_chat(self, chat_id: str) -> bool:
        with self.lock:
            cursor = self.connection.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
            self.connection.commit()
        return cursor.rowcount > 0

    def add_message(self, chat_id: str, role: str, content: str, model_id: str | None) -> MessageRecord:
        now = self._now_iso()
        message_id = str(uuid.uuid4())
        with self.lock:
            self.connection.execute(
                "INSERT INTO messages(id, chat_id, role, content, model_id, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (message_id, chat_id, role, content, model_id, now),
            )
            self.connection.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
            self.connection.commit()

        return MessageRecord(
            id=message_id,
            chat_id=chat_id,
            role=role,
            content=content,
            model_id=model_id,
            created_at=self._as_datetime(now),
        )