import enum
from decimal import Decimal
from typing import Any

from sqlmodel import JSON, Column, Field, SQLModel

from app.models.device import Brand, DeviceCategory


class QuestionType(str, enum.Enum):
    single_select = "single_select"
    multi_select = "multi_select"
    boolean = "boolean"
    # ARCHITECTURE.md §5 only lists these three, but seed-data/questions.json
    # uses "device_selector" for the storage-capacity question (selects the
    # device row / base_price rather than contributing a deduction - see
    # ARCHITECTURE.md §6 and questions.json's own notes on that question).
    # TODO(assumption): added here rather than silently dropping the type.
    device_selector = "device_selector"


class DeductionType(str, enum.Enum):
    percentage = "percentage"
    fixed = "fixed"


class DisqualifyStatus(str, enum.Enum):
    rejected = "rejected"
    manual_review = "manual_review"


class QuestionSet(SQLModel, table=True):
    __tablename__ = "question_sets"

    id: int | None = Field(default=None, primary_key=True)
    category: DeviceCategory
    # Nullable so a future category can be brand-agnostic - see ARCHITECTURE.md §5.
    brand: Brand | None = None
    name: str


class Question(SQLModel, table=True):
    __tablename__ = "questions"

    id: int | None = Field(default=None, primary_key=True)
    question_set_id: int = Field(foreign_key="question_sets.id", index=True)
    text: str
    type: QuestionType
    display_order: int
    options: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    depends_on_question_id: int | None = Field(default=None, foreign_key="questions.id")
    depends_on_value: str | None = None
    # TODO(assumption): ARCHITECTURE.md §5 doesn't define a storage column
    # for device-attribute gating, but §6 explicitly describes filtering
    # questions against device attributes (has_s_pen) before rendering, and
    # seed-data/questions.json's s_pen_working question carries
    # "requires_device_attribute": "has_s_pen" that needs somewhere to live.
    # Added this column to make that gating persistable; flag for review.
    requires_device_attribute: str | None = None


class DeductionRule(SQLModel, table=True):
    __tablename__ = "deduction_rules"

    id: int | None = Field(default=None, primary_key=True)
    question_id: int = Field(foreign_key="questions.id", index=True)
    option_value: str
    deduction_type: DeductionType
    deduction_value: Decimal = Field(max_digits=8, decimal_places=2)
    is_disqualifying: bool = False
    # If is_disqualifying, deduction_value is ignored and the quote's status
    # is set to this instead - see ARCHITECTURE.md §5/§6.
    disqualify_status: DisqualifyStatus | None = None
