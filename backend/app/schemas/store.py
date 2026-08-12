from typing import Any

from pydantic import BaseModel, ConfigDict


class StoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address_line: str
    city: str
    postal_code: str
    lat: float
    lng: float
    opening_hours: dict[str, Any]
    is_active: bool
