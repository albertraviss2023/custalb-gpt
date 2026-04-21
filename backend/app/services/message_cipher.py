from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


ENC_PREFIX = "enc:v1:"


class MessageCipher:
    def __init__(self, key: str) -> None:
        self.fernet = Fernet(key.encode("utf-8"))

    @classmethod
    def from_optional_key(cls, key: str | None) -> MessageCipher | None:
        if not key:
            return None
        return cls(key=key)

    def encrypt(self, plaintext: str) -> str:
        token = self.fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")
        return f"{ENC_PREFIX}{token}"

    def decrypt(self, value: str) -> str:
        if not value.startswith(ENC_PREFIX):
            return value

        token = value[len(ENC_PREFIX) :]
        try:
            return self.fernet.decrypt(token.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ValueError("Unable to decrypt message with current key") from exc
