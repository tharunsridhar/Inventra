import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import (
    InventoryTransaction,
    NotificationType,
    Product,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    TransactionType,
    User,
)
from app.schemas import (
    InvoiceRead,
    Page,
    SalesOrderCreate,
    SalesOrderItemRead,
    SalesOrderRead,
    SalesOrderUpdate,
)
from app.utils import check_and_notify_stock, notify, now

router = APIRouter(prefix="/sales-orders", tags=["sales-orders"])

# Admin/Manager/Employee can all sell - only returns/damage need Manager+
can_sell = require_role("admin", "manager", "employee")


def get_so_or_404(db: Session, sales_order_id: uuid.UUID) -> SalesOrder:
    so = (
        db.query(SalesOrder).options(joinedload(SalesOrder.items)).filter(SalesOrder.id == sales_order_id).first()
    )
    if so is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sales order not found")
    return so


def get_active_product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {product_id} not found or inactive")
    return product


@router.get("", response_model=Page[SalesOrderRead])
def list_sales_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status_filter: SalesOrderStatus | None = Query(default=None, alias="status"),
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(SalesOrder).options(joinedload(SalesOrder.items))
    if status_filter is not None:
        query = query.filter(SalesOrder.status == status_filter)
    if start_date is not None:
        query = query.filter(SalesOrder.created_at >= start_date)
    if end_date is not None:
        query = query.filter(SalesOrder.created_at <= end_date)
    total = query.distinct().count()
    items = query.order_by(SalesOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).distinct().all()
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{sales_order_id}", response_model=SalesOrderRead)
def get_sales_order(sales_order_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    return get_so_or_404(db, sales_order_id)


@router.get("/{sales_order_id}/invoice", response_model=InvoiceRead)
def get_invoice(sales_order_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    so = get_so_or_404(db, sales_order_id)
    if so.status != SalesOrderStatus.COMPLETED or so.invoice_number is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invoice is not available until the sales order is completed")
    total_amount = sum((item.quantity * item.unit_price for item in so.items))
    return InvoiceRead(
        sales_order_id=so.id,
        invoice_number=so.invoice_number,
        invoiced_at=so.invoiced_at,
        customer_name=so.customer_name,
        customer_phone=so.customer_phone,
        items=[SalesOrderItemRead.model_validate(i) for i in so.items],
        total_amount=total_amount,
    )


@router.post("", response_model=SalesOrderRead, status_code=status.HTTP_201_CREATED)
def create_sales_order(payload: SalesOrderCreate, db: Session = Depends(get_db), current_user: User = Depends(can_sell)):
    # price gets snapshotted from the product's current selling price at the
    # moment the order is created, not looked up again later
    items = []
    for item in payload.items:
        product = get_active_product(db, item.product_id)
        items.append(SalesOrderItem(product_id=item.product_id, quantity=item.quantity, unit_price=product.selling_price))

    so = SalesOrder(customer_name=payload.customer_name, customer_phone=payload.customer_phone, created_by=current_user.id)
    so.items = items
    db.add(so)
    db.commit()
    db.refresh(so)
    return so


@router.patch("/{sales_order_id}", response_model=SalesOrderRead, dependencies=[Depends(can_sell)])
def update_sales_order(sales_order_id: uuid.UUID, payload: SalesOrderUpdate, db: Session = Depends(get_db)):
    so = get_so_or_404(db, sales_order_id)
    if so.status != SalesOrderStatus.CREATED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sales order can no longer be modified once completed")

    if payload.customer_name is not None:
        so.customer_name = payload.customer_name
    if payload.customer_phone is not None:
        so.customer_phone = payload.customer_phone

    if payload.items is not None:
        new_items = []
        for item in payload.items:
            product = get_active_product(db, item.product_id)
            new_items.append(SalesOrderItem(product_id=item.product_id, quantity=item.quantity, unit_price=product.selling_price))
        so.items.clear()
        so.items = new_items

    db.commit()
    db.refresh(so)
    return so


@router.post("/{sales_order_id}/complete", response_model=SalesOrderRead)
def complete_sales_order(sales_order_id: uuid.UUID, db: Session = Depends(get_db), current_user: User = Depends(can_sell)):
    so = get_so_or_404(db, sales_order_id)
    if so.status == SalesOrderStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Sales order has already been completed")

    try:
        # check stock for every line item FIRST - if any one item can't be
        # fulfilled, the whole sale is rejected, nothing gets deducted
        products_by_item = {}
        for item in so.items:
            product = db.query(Product).filter(Product.id == item.product_id).first()
            if product is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Product {item.product_id} no longer exists")
            if product.current_stock < item.quantity:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Insufficient stock for '{product.name}': available {product.current_stock}, requested {item.quantity}",
                )
            products_by_item[item.id] = product

        for item in so.items:
            product = products_by_item[item.id]
            product.current_stock -= item.quantity
            db.add(
                InventoryTransaction(
                    product_id=product.id,
                    quantity=item.quantity,
                    transaction_type=TransactionType.SALE,
                    reference_id=so.id,
                    created_by=current_user.id,
                )
            )
            check_and_notify_stock(db, product)

        so.status = SalesOrderStatus.COMPLETED
        so.invoice_number = f"INV-{uuid.uuid4().hex[:10].upper()}"
        so.invoiced_at = now()
        if so.created_by:
            notify(db, so.created_by, NotificationType.SALE_COMPLETED, f"Sales order {so.id} has been completed", so.id)

        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(so)
    return so
