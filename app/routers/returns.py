import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import (
    InventoryTransaction,
    Product,
    Return,
    ReturnStatus,
    SalesOrder,
    SalesOrderStatus,
    TransactionType,
    User,
)
from app.schemas import Page, ReturnCreate, ReturnRead

router = APIRouter(prefix="/returns", tags=["returns"])

manager_or_admin = require_role("admin", "manager")


def get_return_or_404(db: Session, return_id: uuid.UUID) -> Return:
    ret = db.query(Return).filter(Return.id == return_id).first()
    if ret is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return not found")
    return ret


@router.get("", response_model=Page[ReturnRead], dependencies=[Depends(manager_or_admin)])
def list_returns(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: ReturnStatus | None = Query(default=None, alias="status"),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Return)
    if status_filter is not None:
        query = query.filter(Return.status == status_filter)
    if start_date is not None:
        query = query.filter(Return.created_at >= start_date)
    if end_date is not None:
        query = query.filter(Return.created_at <= end_date)
    total = query.count()
    items = query.order_by(Return.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{return_id}", response_model=ReturnRead, dependencies=[Depends(manager_or_admin)])
def get_return(return_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_return_or_404(db, return_id)


@router.post("", response_model=ReturnRead, status_code=status.HTTP_201_CREATED)
def create_return(payload: ReturnCreate, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    so = db.query(SalesOrder).filter(SalesOrder.id == payload.sales_order_id).first()
    if so is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales order not found")
    if so.status != SalesOrderStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Returns can only be filed against a completed sales order")

    sold_quantity = sum(item.quantity for item in so.items if item.product_id == payload.product_id)
    if sold_quantity == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This product was not part of the original sales order")

    # count both pending AND approved returns here - if we only counted
    # approved ones, two pending requests could later both get approved and
    # together return more than was actually sold
    already_reserved_rows = (
        db.query(Return)
        .filter(
            Return.sales_order_id == payload.sales_order_id,
            Return.product_id == payload.product_id,
            Return.status.in_([ReturnStatus.PENDING, ReturnStatus.APPROVED]),
        )
        .all()
    )
    already_reserved = sum(r.quantity for r in already_reserved_rows)
    remaining = sold_quantity - already_reserved
    if payload.quantity > remaining:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Return quantity exceeds remaining returnable quantity ({remaining})")

    ret = Return(
        sales_order_id=payload.sales_order_id,
        product_id=payload.product_id,
        quantity=payload.quantity,
        reason=payload.reason,
        created_by=current_user.id,
    )
    db.add(ret)
    db.commit()
    db.refresh(ret)
    return ret


@router.patch("/{return_id}/approve", response_model=ReturnRead)
def approve_return(return_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    ret = get_return_or_404(db, return_id)
    if ret.status == ReturnStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Return has already been approved")

    try:
        product = db.query(Product).filter(Product.id == ret.product_id).first()
        if product is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product no longer exists")

        product.current_stock += ret.quantity
        db.add(
            InventoryTransaction(
                product_id=product.id,
                quantity=ret.quantity,
                transaction_type=TransactionType.RETURN,
                reference_id=ret.id,
                created_by=current_user.id,
            )
        )
        ret.status = ReturnStatus.APPROVED
        ret.approved_by = current_user.id

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(ret)
    return ret
