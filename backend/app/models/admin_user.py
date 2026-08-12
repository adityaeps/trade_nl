from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlmodel import Field, SQLModel


class AdminUser(SQLModel, table=True):
    """Staff login for the admin panel.

    Not in ARCHITECTURE.md §5's table list - §3 specifies "JWT-based, admin
    only. No customer accounts for MVP" without defining where admin
    credentials live, so this table is the minimum needed to make that work.

    `can_view_payouts` implements §5's requirement that payout records
    "should only be readable by admin roles with a specific `payouts`
    permission, not the general admin role" - kept as a single boolean
    rather than a full RBAC system, which would be over-built for MVP.
    """

    __tablename__ = "admin_users"

    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    is_active: bool = True
    can_view_payouts: bool = False
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), sa_type=DateTime(timezone=True)
    )
