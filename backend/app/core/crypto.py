from cryptography.fernet import Fernet
from sqlalchemy import String
from sqlalchemy.types import TypeDecorator

from app.core.config import settings


class EncryptedString(TypeDecorator):
    """Transparently encrypts/decrypts a string column at rest (Fernet).

    Used for `payouts.iban` per ARCHITECTURE.md §5's encryption note - the
    column stores ciphertext, application code always sees plaintext.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value: str | None, dialect) -> str | None:
        if value is None:
            return value
        return Fernet(settings.encryption_key.encode()).encrypt(value.encode()).decode()

    def process_result_value(self, value: str | None, dialect) -> str | None:
        if value is None:
            return value
        return Fernet(settings.encryption_key.encode()).decrypt(value.encode()).decode()
