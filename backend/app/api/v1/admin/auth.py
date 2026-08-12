from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session, select

from app.core.deps import get_current_admin
from app.core.security import create_access_token, verify_password
from app.db.session import get_session
from app.models.admin_user import AdminUser

router = APIRouter(prefix="/auth", tags=["admin:auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    can_view_payouts: bool


class MeResponse(BaseModel):
    email: str
    can_view_payouts: bool


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_session)):
    admin = session.exec(select(AdminUser).where(AdminUser.email == payload.email)).first()
    # Same error for unknown email and wrong password - don't leak which
    # accounts exist.
    if not admin or not admin.is_active or not verify_password(
        payload.password, admin.hashed_password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return TokenResponse(
        access_token=create_access_token(subject=admin.email),
        email=admin.email,
        can_view_payouts=admin.can_view_payouts,
    )


@router.get("/me", response_model=MeResponse)
def me(admin: AdminUser = Depends(get_current_admin)):
    return MeResponse(email=admin.email, can_view_payouts=admin.can_view_payouts)
