from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    create_refresh_token_value,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import get_db
from app.models import RefreshToken, Role, User
from app.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
    user_to_read,
)
from app.utils import now

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    access_token = create_access_token(user.id, user.role.name)
    refresh_value = create_refresh_token_value()
    expires_at = now() + timedelta(days=settings.refresh_token_expire_days)
    db.add(RefreshToken(user_id=user.id, token=refresh_value, expires_at=expires_at))
    db.commit()
    return TokenResponse(access_token=access_token, refresh_token=refresh_value)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    # anyone can self-register, but they always come in as "employee" -
    # only an admin can promote someone via /users/{id}/role
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    employee_role = db.query(Role).filter(Role.name == "employee").first()

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=employee_role.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_read(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None or not user.is_active or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return _issue_tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    stored = db.query(RefreshToken).filter(RefreshToken.token == payload.refresh_token).first()
    if stored is None or stored.revoked:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token is invalid or revoked")
    if stored.expires_at < now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired")

    user = db.query(User).filter(User.id == stored.user_id).first()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User account is not active")

    return _issue_tokens(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)):
    stored = db.query(RefreshToken).filter(RefreshToken.token == payload.refresh_token).first()
    if stored is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refresh token not found")
    stored.revoked = True
    db.commit()


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return user_to_read(current_user)
