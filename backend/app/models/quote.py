import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime
from sqlmodel import JSON, Column, Field, SQLModel


class QuoteStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    expired = "expired"
    inspected = "inspected"
    paid = "paid"
    # A disqualifying-but-inspectable answer was given (e.g. water damage) -
    # no automatic price shown, staff reviews after the device arrives.
    manual_review = "manual_review"
    # A hard-exclusion answer was given (e.g. SIM-locked) - no price offered,
    # no inspection needed. See ARCHITECTURE.md §5/§6.
    rejected = "rejected"


class FulfillmentMethod(str, enum.Enum):
    store = "store"
    courier = "courier"


class Quote(SQLModel, table=True):
    __tablename__ = "quotes"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    device_id: uuid.UUID = Field(foreign_key="devices.id", index=True)
    answers: dict[str, str] = Field(default_factory=dict, sa_column=Column(JSON))
    base_price_at_quote: Decimal = Field(max_digits=8, decimal_places=2)
    # Null when disqualified (rejected/manual_review) - see ARCHITECTURE.md §6.
    calculated_price: Decimal | None = Field(default=None, max_digits=8, decimal_places=2)
    status: QuoteStatus = QuoteStatus.pending
    fulfillment_method: FulfillmentMethod | None = None
    store_id: int | None = Field(default=None, foreign_key="stores.id")
    # TODO(assumption): ARCHITECTURE.md §5 doesn't mark these nullable, but
    # POST /quotes (§8) only takes {device_id, answers} - customer details
    # aren't collected until POST /quotes/{id}/confirm. Making these nullable
    # to match the documented API flow rather than the literal schema table.
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    valid_until: datetime = Field(sa_type=DateTime(timezone=True))
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )
