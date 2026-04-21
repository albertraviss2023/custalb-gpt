from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import UTC, datetime

from app.models.schemas import ChatDetail, ChatSummary, LogEventRecord, MessageRecord
from app.models.schemas import UploadRecord
from app.services.message_cipher import MessageCipher


class Repository:
    def __init__(self, connection: sqlite3.Connection, message_cipher: MessageCipher | None = None) -> None:
        self.connection = connection
        self.lock = threading.Lock()
        self.message_cipher = message_cipher

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _as_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)

    @staticmethod
    def _build_summary_from_messages(rows: list[sqlite3.Row]) -> str:
        if not rows:
            return ""
        snippets: list[str] = []
        for row in rows[-24:]:
            role = str(row["role"]).strip().lower()
            raw = str(row["content"]).strip().replace("\n", " ")
            if not raw:
                continue
            if len(raw) > 180:
                raw = raw[:180].rstrip(" ,.;:-") + "..."
            actor = "User" if role == "user" else "Assistant"
            snippets.append(f"- {actor}: {raw}")
        if not snippets:
            return ""
        return "Inherited chat summary:\n" + "\n".join(snippets)

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

    def create_chat_with_inheritance(
        self,
        *,
        title: str,
        selected_model_id: str | None,
        source_chat_id: str,
        inherit_recent_messages: int = 12,
    ) -> ChatSummary:
        source_chat = self.get_chat(source_chat_id)
        if not source_chat:
            raise ValueError("Source chat not found")

        inherit_count = max(0, min(inherit_recent_messages, 100))
        now = self._now_iso()
        chat_id = str(uuid.uuid4())
        source_memory = self.get_chat_memory(source_chat_id)
        source_rows_for_summary = self.connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE chat_id = ?
            ORDER BY created_at ASC
            """,
            (source_chat_id,),
        ).fetchall()
        fallback_summary = self._build_summary_from_messages(source_rows_for_summary)

        with self.lock:
            self.connection.execute(
                "INSERT INTO chats(id, title, selected_model_id, created_at, updated_at) VALUES(?, ?, ?, ?, ?)",
                (chat_id, title, selected_model_id, now, now),
            )

            if inherit_count > 0:
                source_rows = self.connection.execute(
                    """
                    SELECT role, content, model_id
                    FROM messages
                    WHERE chat_id = ?
                    ORDER BY created_at DESC
                    LIMIT ?
                    """,
                    (source_chat_id, inherit_count),
                ).fetchall()
                for row in reversed(source_rows):
                    self.connection.execute(
                        """
                        INSERT INTO messages(id, chat_id, role, content, model_id, created_at)
                        VALUES(?, ?, ?, ?, ?, ?)
                        """,
                        (str(uuid.uuid4()), chat_id, row["role"], row["content"], row["model_id"], now),
                    )

            inherited_summary_text = ""
            inherited_summary_version = 1
            inherited_compaction_count = 0
            inherited_last_compacted_message_id = None
            inherited_token_estimate = 0

            if source_memory:
                inherited_summary_text = str(source_memory.get("summary_text", ""))
                inherited_summary_version = int(source_memory.get("summary_version", 0))
                inherited_compaction_count = int(source_memory.get("compaction_count", 0))
                inherited_last_compacted_message_id = source_memory.get("last_compacted_message_id")
                inherited_token_estimate = max(0, int(source_memory.get("token_estimate", 0)))

            if not inherited_summary_text.strip():
                inherited_summary_text = fallback_summary
                if inherited_summary_text:
                    inherited_summary_version = max(1, inherited_summary_version)
                    inherited_compaction_count = max(1, inherited_compaction_count)
                    inherited_token_estimate = max(inherited_token_estimate, len(inherited_summary_text) // 4)

            if inherited_summary_text.strip():
                self.connection.execute(
                    """
                    INSERT INTO chat_memory(
                        chat_id, summary_text, summary_version, compaction_count, last_compacted_message_id, token_estimate, updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chat_id,
                        inherited_summary_text,
                        inherited_summary_version,
                        inherited_compaction_count,
                        inherited_last_compacted_message_id,
                        inherited_token_estimate,
                        now,
                    ),
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

        messages = []
        for row in message_rows:
            raw_content = str(row["content"])
            content = raw_content
            if self.message_cipher:
                try:
                    content = self.message_cipher.decrypt(raw_content)
                except ValueError:
                    content = "[Encrypted message unavailable with current key]"
            messages.append(
                MessageRecord(
                    id=str(row["id"]),
                    chat_id=str(row["chat_id"]),
                    role=str(row["role"]),
                    content=content,
                    model_id=row["model_id"],
                    created_at=self._as_datetime(str(row["created_at"])),
                )
            )

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
        stored_content = self.message_cipher.encrypt(content) if self.message_cipher else content
        with self.lock:
            self.connection.execute(
                "INSERT INTO messages(id, chat_id, role, content, model_id, created_at) VALUES(?, ?, ?, ?, ?, ?)",
                (message_id, chat_id, role, stored_content, model_id, now),
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

    def replace_assistant_message(
        self,
        *,
        chat_id: str,
        message_id: str,
        content: str,
        model_id: str | None,
    ) -> bool:
        existing = self.connection.execute(
            "SELECT id FROM messages WHERE id = ? AND chat_id = ? AND role = 'assistant'",
            (message_id, chat_id),
        ).fetchone()
        if not existing:
            return False

        now = self._now_iso()
        stored_content = self.message_cipher.encrypt(content) if self.message_cipher else content
        with self.lock:
            self.connection.execute(
                "UPDATE messages SET content = ?, model_id = ? WHERE id = ? AND chat_id = ?",
                (stored_content, model_id, message_id, chat_id),
            )
            self.connection.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
            self.connection.commit()
        return True

    def list_installed_addons(self) -> dict[str, datetime]:
        rows = self.connection.execute(
            "SELECT addon_id, installed_at FROM addons_installed ORDER BY installed_at DESC"
        ).fetchall()
        return {str(row["addon_id"]): self._as_datetime(str(row["installed_at"])) for row in rows}

    def install_addon(self, addon_id: str) -> datetime:
        now = self._now_iso()
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO addons_installed(addon_id, installed_at)
                VALUES(?, ?)
                ON CONFLICT(addon_id) DO UPDATE SET installed_at = excluded.installed_at
                """,
                (addon_id, now),
            )
            self.connection.commit()
        return self._as_datetime(now)

    def uninstall_addon(self, addon_id: str) -> bool:
        with self.lock:
            cursor = self.connection.execute("DELETE FROM addons_installed WHERE addon_id = ?", (addon_id,))
            self.connection.commit()
        return cursor.rowcount > 0

    def create_upload(
        self,
        *,
        upload_id: str,
        original_name: str,
        mime_type: str | None,
        total_size_bytes: int,
        storage_path: str,
    ) -> UploadRecord:
        now = self._now_iso()
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO uploads(id, original_name, mime_type, total_size_bytes, received_bytes, storage_path, status, created_at, updated_at)
                VALUES(?, ?, ?, ?, 0, ?, 'pending', ?, ?)
                """,
                (upload_id, original_name, mime_type, total_size_bytes, storage_path, now, now),
            )
            self.connection.commit()
        return UploadRecord(
            id=upload_id,
            original_name=original_name,
            mime_type=mime_type,
            total_size_bytes=total_size_bytes,
            received_bytes=0,
            status="pending",
            created_at=self._as_datetime(now),
            updated_at=self._as_datetime(now),
        )

    def get_upload(self, upload_id: str) -> UploadRecord | None:
        row = self.connection.execute(
            """
            SELECT id, original_name, mime_type, total_size_bytes, received_bytes, status, created_at, updated_at
            FROM uploads
            WHERE id = ?
            """,
            (upload_id,),
        ).fetchone()
        if not row:
            return None
        return UploadRecord(
            id=str(row["id"]),
            original_name=str(row["original_name"]),
            mime_type=row["mime_type"],
            total_size_bytes=int(row["total_size_bytes"]),
            received_bytes=int(row["received_bytes"]),
            status=str(row["status"]),
            created_at=self._as_datetime(str(row["created_at"])),
            updated_at=self._as_datetime(str(row["updated_at"])),
        )

    def get_upload_storage_path(self, upload_id: str) -> str | None:
        row = self.connection.execute("SELECT storage_path FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        if not row:
            return None
        return str(row["storage_path"])

    def list_uploads(self) -> list[UploadRecord]:
        rows = self.connection.execute(
            """
            SELECT id, original_name, mime_type, total_size_bytes, received_bytes, status, created_at, updated_at
            FROM uploads
            ORDER BY created_at DESC
            """
        ).fetchall()
        return [
            UploadRecord(
                id=str(row["id"]),
                original_name=str(row["original_name"]),
                mime_type=row["mime_type"],
                total_size_bytes=int(row["total_size_bytes"]),
                received_bytes=int(row["received_bytes"]),
                status=str(row["status"]),
                created_at=self._as_datetime(str(row["created_at"])),
                updated_at=self._as_datetime(str(row["updated_at"])),
            )
            for row in rows
        ]

    def list_uploads_by_ids(self, upload_ids: list[str]) -> list[UploadRecord]:
        if not upload_ids:
            return []
        placeholders = ",".join("?" for _ in upload_ids)
        rows = self.connection.execute(
            f"""
            SELECT id, original_name, mime_type, total_size_bytes, received_bytes, status, created_at, updated_at
            FROM uploads
            WHERE id IN ({placeholders})
            ORDER BY created_at DESC
            """,
            tuple(upload_ids),
        ).fetchall()
        return [
            UploadRecord(
                id=str(row["id"]),
                original_name=str(row["original_name"]),
                mime_type=row["mime_type"],
                total_size_bytes=int(row["total_size_bytes"]),
                received_bytes=int(row["received_bytes"]),
                status=str(row["status"]),
                created_at=self._as_datetime(str(row["created_at"])),
                updated_at=self._as_datetime(str(row["updated_at"])),
            )
            for row in rows
        ]

    def update_upload_progress(self, upload_id: str, *, received_bytes: int, status: str) -> UploadRecord | None:
        now = self._now_iso()
        with self.lock:
            self.connection.execute(
                "UPDATE uploads SET received_bytes = ?, status = ?, updated_at = ? WHERE id = ?",
                (received_bytes, status, now, upload_id),
            )
            self.connection.commit()
        return self.get_upload(upload_id)

    def delete_upload(self, upload_id: str) -> str | None:
        row = self.connection.execute("SELECT storage_path FROM uploads WHERE id = ?", (upload_id,)).fetchone()
        if not row:
            return None
        storage_path = str(row["storage_path"])
        with self.lock:
            self.connection.execute("DELETE FROM uploads WHERE id = ?", (upload_id,))
            self.connection.commit()
        return storage_path

    def add_log_event(
        self,
        *,
        level: str,
        source: str,
        message: str,
        context: dict[str, object] | None = None,
        chat_id: str | None = None,
    ) -> LogEventRecord:
        now = self._now_iso()
        event_id = str(uuid.uuid4())
        context_json = json.dumps(context or {}, ensure_ascii=True)
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO app_logs(id, level, source, message, chat_id, context_json, created_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (event_id, level, source, message, chat_id, context_json, now),
            )
            self.connection.commit()
        return LogEventRecord(
            id=event_id,
            level=level,
            source=source,
            message=message,
            chat_id=chat_id,
            context=context or {},
            created_at=self._as_datetime(now),
        )

    def list_log_events(self, *, limit: int = 100) -> list[LogEventRecord]:
        safe_limit = max(1, min(limit, 500))
        rows = self.connection.execute(
            """
            SELECT id, level, source, message, chat_id, context_json, created_at
            FROM app_logs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
        events: list[LogEventRecord] = []
        for row in rows:
            context: dict[str, object] = {}
            raw_context = row["context_json"]
            if isinstance(raw_context, str):
                try:
                    parsed = json.loads(raw_context)
                    if isinstance(parsed, dict):
                        context = parsed
                except json.JSONDecodeError:
                    context = {}
            events.append(
                LogEventRecord(
                    id=str(row["id"]),
                    level=str(row["level"]),
                    source=str(row["source"]),
                    message=str(row["message"]),
                    chat_id=row["chat_id"],
                    context=context,
                    created_at=self._as_datetime(str(row["created_at"])),
                )
            )
        return events

    def get_chat_memory(self, chat_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            """
            SELECT chat_id, summary_text, summary_version, compaction_count, last_compacted_message_id, token_estimate, updated_at
            FROM chat_memory
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        if not row:
            return None
        return {
            "chat_id": str(row["chat_id"]),
            "summary_text": str(row["summary_text"]),
            "summary_version": int(row["summary_version"]),
            "compaction_count": int(row["compaction_count"]),
            "last_compacted_message_id": row["last_compacted_message_id"],
            "token_estimate": int(row["token_estimate"]),
            "updated_at": self._as_datetime(str(row["updated_at"])),
        }

    def upsert_chat_memory(
        self,
        *,
        chat_id: str,
        summary_text: str,
        summary_version: int,
        compaction_count: int,
        last_compacted_message_id: str | None,
        token_estimate: int,
    ) -> None:
        now = self._now_iso()
        with self.lock:
            self.connection.execute(
                """
                INSERT INTO chat_memory(
                    chat_id, summary_text, summary_version, compaction_count, last_compacted_message_id, token_estimate, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    summary_version = excluded.summary_version,
                    compaction_count = excluded.compaction_count,
                    last_compacted_message_id = excluded.last_compacted_message_id,
                    token_estimate = excluded.token_estimate,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    summary_text,
                    summary_version,
                    compaction_count,
                    last_compacted_message_id,
                    max(0, token_estimate),
                    now,
                ),
            )
            self.connection.commit()

    def compact_chat_context(
        self,
        *,
        chat_id: str,
        delete_message_ids: list[str],
        summary_text: str,
        summary_version: int,
        compaction_count: int,
        last_compacted_message_id: str | None,
        token_estimate: int,
    ) -> None:
        now = self._now_iso()
        with self.lock:
            if delete_message_ids:
                placeholders = ",".join("?" for _ in delete_message_ids)
                self.connection.execute(
                    f"DELETE FROM messages WHERE chat_id = ? AND id IN ({placeholders})",
                    (chat_id, *delete_message_ids),
                )
            self.connection.execute(
                """
                INSERT INTO chat_memory(
                    chat_id, summary_text, summary_version, compaction_count, last_compacted_message_id, token_estimate, updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    summary_text = excluded.summary_text,
                    summary_version = excluded.summary_version,
                    compaction_count = excluded.compaction_count,
                    last_compacted_message_id = excluded.last_compacted_message_id,
                    token_estimate = excluded.token_estimate,
                    updated_at = excluded.updated_at
                """,
                (
                    chat_id,
                    summary_text,
                    summary_version,
                    compaction_count,
                    last_compacted_message_id,
                    max(0, token_estimate),
                    now,
                ),
            )
            self.connection.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
            self.connection.commit()
