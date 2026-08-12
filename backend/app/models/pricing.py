import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class LiquidityTier(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class BasePrice(SQLModel, table=True):
    __tablename__ = "base_prices"

    id: int | None = Field(default=None, primary_key=True)
    device_id: uuid.UUID = Field(foreign_key="devices.id", unique=True, index=True)
    base_price: Decimal = Field(max_digits=8, decimal_places=2)
    liquidity_tier: LiquidityTier
    # Business decision per device, not a global constant - see ARCHITECTURE.md §11.
    markup_pct: Decimal = Field(max_digits=5, decimal_places=2)
    last_synced_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )


class CompetitorPrice(SQLModel, table=True):
    __tablename__ = "competitor_prices"

    id: int | None = Field(default=None, primary_key=True)
    device_id: uuid.UUID = Field(foreign_key="devices.id", index=True)
    competitor_name: str  # 'swappie' | 'buyback'
    price: Decimal = Field(max_digits=8, decimal_places=2)
    condition_tier: str
    source_url: str
    checked_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True)
    )


class PriceHistory(SQLModel, table=True):
    """Append-only, for admin trend charts. Never update rows, only insert."""

    __tablename__ = "price_history"

    id: int | None = Field(default=None, primary_key=True)
    device_id: uuid.UUID = Field(foreign_key="devices.id", index=True)
    base_price: Decimal = Field(max_digits=8, decimal_places=2)
    recorded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True)
    )
