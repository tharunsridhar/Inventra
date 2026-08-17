import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.auth import require_role
from app.database import get_db
from app.models import (
    InventoryTransaction,
    NotificationType,
    Product,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    Supplier,
    TransactionType,
    User,
)
from app.schemas import Page, PurchaseOrderCreate, PurchaseOrderRead, PurchaseOrderUpdate
from app.utils import check_and_notify_stock, notify, now

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])

manager_or_admin = require_role("admin", "manager")


def get_po_or_404(db: Session, purchase_order_id: uuid.UUID) -> PurchaseOrder:
    po = (
        db.query(PurchaseOrder)
        .options(joinedload(PurchaseOrder.items))
        .filter(PurchaseOrder.id == purchase_order_id)
        .first()
    )
    if po is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return po


def get_po_for_update_or_404(db: Session, purchase_order_id: uuid.UUID) -> PurchaseOrder:
    # SELECT ... FOR UPDATE on the PO row itself, so two concurrent /receive
    # calls on the same PO can't both read status="ordered" before either
    # commits. Postgres won't allow FOR UPDATE combined with the outer join
    # that joinedload(items) produces, so this is a separate, plain query -
    # `po.items` is loaded lazily afterwards instead.
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == purchase_order_id).with_for_update().first()
    if po is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Purchase order not found")
    return po


@router.get("", response_model=Page[PurchaseOrderRead], dependencies=[Depends(manager_or_admin)])
def list_purchase_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: PurchaseOrderStatus | None = Query(default=None, alias="status"),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.items))
    if status_filter is not None:
        query = query.filter(PurchaseOrder.status == status_filter)
    if start_date is not None:
        query = query.filter(PurchaseOrder.created_at >= start_date)
    if end_date is not None:
        query = query.filter(PurchaseOrder.created_at <= end_date)
    total = query.distinct().count()
    items = (
        query.order_by(PurchaseOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).distinct().all()
    )
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{purchase_order_id}", response_model=PurchaseOrderRead, dependencies=[Depends(manager_or_admin)])
def get_purchase_order(purchase_order_id: uuid.UUID, db: Session = Depends(get_db)):
    return get_po_or_404(db, purchase_order_id)


@router.post("", response_model=PurchaseOrderRead, status_code=status.HTTP_201_CREATED)
def create_purchase_order(payload: PurchaseOrderCreate, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    supplier = db.query(Supplier).filter(Supplier.id == payload.supplier_id).first()
    if supplier is None or not supplier.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier not found or inactive")

    for item in payload.items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product is None or not product.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {item.product_id} not found or inactive")

    po = PurchaseOrder(supplier_id=payload.supplier_id, created_by=current_user.id)
    po.items = [
        PurchaseOrderItem(product_id=item.product_id, quantity=item.quantity, unit_cost=item.unit_cost)
        for item in payload.items
    ]
    db.add(po)
    db.commit()
    db.refresh(po)
    return po


@router.patch("/{purchase_order_id}", response_model=PurchaseOrderRead, dependencies=[Depends(manager_or_admin)])
def update_purchase_order(purchase_order_id: uuid.UUID, payload: PurchaseOrderUpdate, db: Session = Depends(get_db)):
    po = get_po_or_404(db, purchase_order_id)
    if po.status != PurchaseOrderStatus.ORDERED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase order can no longer be modified once received")

    if payload.supplier_id is not None:
        supplier = db.query(Supplier).filter(Supplier.id == payload.supplier_id).first()
        if supplier is None or not supplier.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier not found or inactive")
        po.supplier_id = payload.supplier_id

    if payload.items is not None:
        for item in payload.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product is None or not product.is_active:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {item.product_id} not found or inactive")
        po.items.clear()
        po.items = [
            PurchaseOrderItem(product_id=item.product_id, quantity=item.quantity, unit_cost=item.unit_cost)
            for item in payload.items
        ]

    db.commit()
    db.refresh(po)
    return po


@router.post("/{purchase_order_id}/receive", response_model=PurchaseOrderRead)
def receive_purchase_order(purchase_order_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    po = get_po_for_update_or_404(db, purchase_order_id)
    if po.status == PurchaseOrderStatus.RECEIVED:
        # already received - don't double-count the stock, just say no
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Purchase order has already been received")

    # everything below happens as one transaction: if anything fails partway
    # through, we roll back so we never end up with half-applied stock changes
    try:
        # lock product rows in a fixed order (by id) - if two orders share
        # products, every transaction that touches both always locks them in
        # the same order, so they queue up instead of deadlocking each other
        for item in sorted(po.items, key=lambda i: i.product_id):
            product = db.query(Product).filter(Product.id == item.product_id).with_for_update().first()
            if product is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {item.product_id} no longer exists")

            product.current_stock += item.quantity
            db.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity=item.quantity,
                    transaction_type=TransactionType.PURCHASE,
                    reference_id=po.id,
                    created_by=current_user.id,
                )
            )
            check_and_notify_stock(db, product)

        po.status = PurchaseOrderStatus.RECEIVED
        po.received_at = now()
        if po.created_by:
            notify(db, po.created_by, NotificationType.PURCHASE_COMPLETED, f"Purchase order {po.id} has been received", po.id)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(po)
    return po
