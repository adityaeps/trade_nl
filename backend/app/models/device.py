import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class Brand(str, enum.Enum):
    apple = "apple"
    samsung = "samsung"


class DeviceCategory(str, enum.Enum):
    phone = "phone"
    tablet = "tablet"
    watch = "watch"


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    brand: Brand
    model: str
    storage_gb: int
    color: str | None = None
    category: DeviceCategory = DeviceCategory.phone
    has_s_pen: bool = False
    slug: str = Field(unique=True, index=True)
    image_url: str | None = None
    is_active: bool = True
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        sa_column_kwargs={"onupdate": lambda: datetime.now(timezone.utc)},
    )
