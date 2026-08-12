"""Shared FastAPI dependencies for admin authentication."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.core.security import decode_access_token
from app.db.session import get_session
from app.models.admin_user import AdminUser

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> AdminUser:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    email = decode_access_token(credentials.credentials)
    if not email:
        raise unauthorized

    admin = session.exec(select(AdminUser).where(AdminUser.email == email)).first()
    if not admin or not admin.is_active:
        raise unauthorized
    return admin


def require_payouts_permission(admin: AdminUser = Depends(get_current_admin)) -> AdminUser:
    """Gate for payout data - ARCHITECTURE.md §5 requires payouts be readable
    only by admins with a specific payouts permission, not every admin."""
    if not admin.can_view_payouts:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account does not have the payouts permission",
        )
    return admin
