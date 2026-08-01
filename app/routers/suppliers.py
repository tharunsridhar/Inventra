import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Supplier, User
from app.schemas import Page, SupplierCreate, SupplierRead, SupplierUpdate

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

manager_or_admin = require_role("admin", "manager")


@router.get("", response_model=Page[SupplierRead])
def list_suppliers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Supplier).filter(Supplier.is_active.is_(True))
    if search:
        query = query.filter(Supplier.name.ilike(f"%{search}%"))
    total = query.count()
    items = query.order_by(Supplier.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    return supplier


@router.post("", response_model=SupplierRead, status_code=status.HTTP_201_CREATED)
def create_supplier(payload: SupplierCreate, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    if db.query(Supplier).filter(Supplier.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A supplier with this email already exists")
    supplier = Supplier(
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        created_by=current_user.id,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


@router.patch("/{supplier_id}", response_model=SupplierRead, dependencies=[Depends(manager_or_admin)])
def update_supplier(supplier_id: uuid.UUID, payload: SupplierUpdate, db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    if payload.email is not None and payload.email != supplier.email:
        if db.query(Supplier).filter(Supplier.email == payload.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A supplier with this email already exists")
        supplier.email = payload.email
    if payload.name is not None:
        supplier.name = payload.name
    if payload.phone is not None:
        supplier.phone = payload.phone
    if payload.address is not None:
        supplier.address = payload.address
    db.commit()
    db.refresh(supplier)
    return supplier


@router.delete("/{supplier_id}", response_model=SupplierRead, dependencies=[Depends(manager_or_admin)])
def delete_supplier(supplier_id: uuid.UUID, db: Session = Depends(get_db)):
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if supplier is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Supplier not found")
    supplier.is_active = False
    db.commit()
    db.refresh(supplier)
    return supplier
