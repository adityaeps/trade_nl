from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DeviceSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    brand: str
    model: str
    storage_gb: int
    color: str | None
    slug: str
    image_url: str | None
    has_s_pen: bool
    price_up_to: Decimal | None


class DeductionRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    option_value: str
    deduction_type: str
    deduction_value: Decimal
    is_disqualifying: bool
    disqualify_status: str | None


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    type: str
    display_order: int
    options: list[dict[str, Any]]
    depends_on_question_id: int | None
    depends_on_value: str | None
    requires_device_attribute: str | None
    # Exposed so the frontend can render a live price/disqualification
    # preview while answering, without persisting a draft Quote row for
    # every keystroke - quotes are frozen at creation (§2), so there's no
    # "draft quote" concept in the API. The authoritative price always
    # comes from POST /quotes; this is preview-only. See TASKS.md Sprint 4.
    deduction_rules: list[DeductionRuleOut]


class DeviceDetail(DeviceSummary):
    storage_variants: list[DeviceSummary]
    questions: list[QuestionOut]
