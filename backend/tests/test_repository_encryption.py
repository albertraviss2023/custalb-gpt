from __future__ import annotations

import sqlite3
from pathlib import Path

from cryptography.fernet import Fernet

from app.db.database import create_connection, initialize_database
from app.db.repository import Repository
from app.services.message_cipher import ENC_PREFIX, MessageCipher


def test_repository_encrypts_messages_at_rest(tmp_path: Path) -> None:
    connection = create_connection(tmp_path / "app.db")
    initialize_database(connection)

    key = Fernet.generate_key().decode("utf-8")
    repository = Repository(connection, message_cipher=MessageCipher(key))

    chat = repository.create_chat("Encrypted chat", selected_model_id="gemma4_e4b_8bit")
    repository.add_message(chat.id, "user", "secret question", None)
    repository.add_message(chat.id, "assistant", "secret answer", "gemma4_e4b_8bit")

    row = connection.execute(
        "SELECT content FROM messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT 1",
        (chat.id,),
    ).fetchone()
    assert row is not None
    assert str(row["content"]).startswith(ENC_PREFIX)

    hydrated = repository.get_chat(chat.id)
    assert hydrated is not None
    assert hydrated.messages[-1].content == "secret answer"
    connection.close()


def test_repository_handles_wrong_key_gracefully(tmp_path: Path) -> None:
    database_path = tmp_path / "app.db"
    writer_connection = create_connection(database_path)
    initialize_database(writer_connection)

    writer = Repository(writer_connection, message_cipher=MessageCipher(Fernet.generate_key().decode("utf-8")))
    chat = writer.create_chat("Wrong key", selected_model_id=None)
    writer.add_message(chat.id, "user", "hidden", None)
    writer_connection.close()

    reader_connection = sqlite3.connect(database_path, check_same_thread=False)
    reader_connection.row_factory = sqlite3.Row
    reader = Repository(reader_connection, message_cipher=MessageCipher(Fernet.generate_key().decode("utf-8")))
    hydrated = reader.get_chat(chat.id)
    assert hydrated is not None
    assert hydrated.messages[0].content == "[Encrypted message unavailable with current key]"
    reader_connection.close()
