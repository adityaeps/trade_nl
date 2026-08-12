import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel

from app.core.crypto import EncryptedString


class PayoutStatus(str, enum.Enum):
    pending = "pending"
    paid = "paid"


class Payout(SQLModel, table=True):
    __tablename__ = "payouts"

    id: int | None = Field(default=None, primary_key=True)
    quote_id: uuid.UUID = Field(foreign_key="quotes.id", unique=True, index=True)
    # Encrypted at rest - see ARCHITECTURE.md §5 and app/core/crypto.py.
    # Should only be readable by admin roles with a specific `payouts`
    # permission, not the general admin role - enforce in the API layer
    # (Sprint 6/8), not here.
    iban: str = Field(sa_column=Column(EncryptedString, nullable=False))
    account_holder_name: str
    amount: Decimal = Field(max_digits=8, decimal_places=2)
    status: PayoutStatus = PayoutStatus.pending
    paid_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True)
    )
