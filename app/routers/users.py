import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import hash_password, require_role
from app.database import get_db
from app.models import Role, User
from app.schemas import (
    AssignRoleRequest,
    Page,
    ResetPasswordRequest,
    UserCreate,
    UserRead,
    UserUpdate,
    user_to_read,
)

router = APIRouter(prefix="/users", tags=["users"])

admin_only = require_role("admin")


def get_user_or_404(db: Session, user_id: uuid.UUID) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.get("", response_model=Page[UserRead], dependencies=[Depends(admin_only)])
def list_users(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db)):
    query = db.query(User)
    total = query.count()
    items = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=[user_to_read(u) for u in items], total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=UserRead, dependencies=[Depends(admin_only)])
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    return user_to_read(get_user_or_404(db, user_id))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")

    role = db.query(Role).filter(Role.name == payload.role.value).first()
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role_id=role.id,
        created_by=current_user.id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_read(user)


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(admin_only)])
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    if payload.email is not None and payload.email != user.email:
        if db.query(User).filter(User.email == payload.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists")
        user.email = payload.email
    if payload.full_name is not None:
        user.full_name = payload.full_name
    db.commit()
    db.refresh(user)
    return user_to_read(user)


@router.patch("/{user_id}/role", response_model=UserRead, dependencies=[Depends(admin_only)])
def assign_role(user_id: uuid.UUID, payload: AssignRoleRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    role = db.query(Role).filter(Role.name == payload.role.value).first()
    user.role_id = role.id
    db.commit()
    db.refresh(user)
    return user_to_read(user)


@router.patch("/{user_id}/reset-password", response_model=UserRead, dependencies=[Depends(admin_only)])
def reset_password(user_id: uuid.UUID, payload: ResetPasswordRequest, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    db.refresh(user)
    return user_to_read(user)


@router.patch("/{user_id}/enable", response_model=UserRead, dependencies=[Depends(admin_only)])
def enable_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_user_or_404(db, user_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user_to_read(user)


@router.delete("/{user_id}", response_model=UserRead, dependencies=[Depends(admin_only)])
def disable_user(user_id: uuid.UUID, db: Session = Depends(get_db)):
    """Soft delete - just flips is_active off, we never actually delete rows."""
    user = get_user_or_404(db, user_id)
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user_to_read(user)
