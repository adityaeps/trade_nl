from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel


class Store(SQLModel, table=True):
    __tablename__ = "stores"

    id: int | None = Field(default=None, primary_key=True)
    name: str
    address_line: str
    city: str
    postal_code: str
    lat: float
    lng: float
    opening_hours: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    is_active: bool = True
