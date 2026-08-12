from sqlmodel import SQLModel

# Import every model module here so Alembic's autogenerate (and SQLModel.metadata
# at runtime) sees all tables. Individual model files should not import each
# other for this purpose - this module is the single registration point.
from app.models.admin_user import AdminUser  # noqa: F401
from app.models.device import Device  # noqa: F401
from app.models.pricing import BasePrice, CompetitorPrice, PriceHistory  # noqa: F401
from app.models.questionnaire import (  # noqa: F401
    DeductionRule,
    Question,
    QuestionSet,
)
from app.models.quote import Quote  # noqa: F401
from app.models.store import Store  # noqa: F401
from app.models.payout import Payout  # noqa: F401

__all__ = ["SQLModel"]
