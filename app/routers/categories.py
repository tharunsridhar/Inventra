import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Category, User
from app.schemas import CategoryCreate, CategoryRead, CategoryUpdate, Page

router = APIRouter(prefix="/categories", tags=["categories"])

manager_or_admin = require_role("admin", "manager")


@router.get("", response_model=Page[CategoryRead])
def list_categories(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Category).filter(Category.is_active.is_(True))
    if search:
        query = query.filter(Category.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(Category.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{category_id}", response_model=CategoryRead)
def get_category(category_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    if db.query(Category).filter(Category.name == payload.name).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A category with this name already exists")
    category = Category(name=payload.name, description=payload.description, created_by=current_user.id)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@router.patch("/{category_id}", response_model=CategoryRead, dependencies=[Depends(manager_or_admin)])
def update_category(category_id: uuid.UUID, payload: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if payload.name is not None:
        category.name = payload.name
    if payload.description is not None:
        category.description = payload.description
    db.commit()
    db.refresh(category)
    return category


@router.delete("/{category_id}", response_model=CategoryRead, dependencies=[Depends(manager_or_admin)])
def delete_category(category_id: uuid.UUID, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    category.is_active = False
    db.commit()
    db.refresh(category)
    return category
