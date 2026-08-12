from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.quote import FulfillmentMethod


class QuoteCreateRequest(BaseModel):
    device_id: UUID
    answers: dict[str, str]


class AnsweredQuestionOut(BaseModel):
    question_id: int
    question_text: str
    selected_value: str
    selected_label: str


class QuoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    device_id: UUID
    answers: dict[str, str]
    # Resolved question text + option label for each answer, in question
    # display order - lets the frontend show what the customer selected
    # without re-fetching the device/questionnaire. Joined live against
    # Question rows rather than snapshotted, same tradeoff as base_price
    # (frozen) vs. everything else (not) - see ARCHITECTURE.md §2.
    answers_detail: list[AnsweredQuestionOut]
    status: str
    base_price_at_quote: Decimal
    calculated_price: Decimal | None
    fulfillment_method: str | None
    store_id: int | None
    customer_name: str | None
    customer_email: str | None
    customer_phone: str | None
    valid_until: datetime


class QuoteConfirmRequest(BaseModel):
    fulfillment_method: FulfillmentMethod
    store_id: int | None = None
    customer_name: str
    customer_email: str
    customer_phone: str
    iban: str
    account_holder_name: str
