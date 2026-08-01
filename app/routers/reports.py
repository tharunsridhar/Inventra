from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, joinedload

from app.auth import require_role
from app.database import get_db
from app.models import InventoryTransaction, Product, PurchaseOrder, SalesOrder, TransactionType
from app.schemas import (
    InventoryReport,
    InventoryReportItem,
    InventoryReportSummary,
    ProductReport,
    ProductReportItem,
    PurchaseReport,
    PurchaseReportItem,
    SalesReport,
    SalesReportItem,
)
from app.utils import now

router = APIRouter(prefix="/reports", tags=["reports"])

manager_or_admin = require_role("admin", "manager")


@router.get("/products", response_model=ProductReport, dependencies=[Depends(manager_or_admin)])
def product_report(start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db)):
    query = db.query(Product)
    if start_date is not None:
        query = query.filter(Product.created_at >= start_date)
    if end_date is not None:
        query = query.filter(Product.created_at <= end_date)
    products = query.order_by(Product.created_at.desc()).all()

    items = [
        ProductReportItem(
            id=p.id, sku=p.sku, name=p.name, category_id=p.category_id, supplier_id=p.supplier_id,
            cost_price=p.cost_price, selling_price=p.selling_price, current_stock=p.current_stock,
            low_stock_threshold=p.low_stock_threshold, is_active=p.is_active,
        )
        for p in products
    ]
    return ProductReport(generated_at=now(), start_date=start_date, end_date=end_date, total_count=len(items), items=items)


@router.get("/purchases", response_model=PurchaseReport, dependencies=[Depends(manager_or_admin)])
def purchase_report(start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db)):
    query = db.query(PurchaseOrder).options(joinedload(PurchaseOrder.items))
    if start_date is not None:
        query = query.filter(PurchaseOrder.created_at >= start_date)
    if end_date is not None:
        query = query.filter(PurchaseOrder.created_at <= end_date)
    orders = query.order_by(PurchaseOrder.created_at.desc()).distinct().all()

    items = []
    total_cost = Decimal("0")
    for po in orders:
        order_total = sum((i.quantity * i.unit_cost for i in po.items), Decimal("0"))
        total_cost += order_total
        items.append(PurchaseReportItem(id=po.id, supplier_id=po.supplier_id, status=po.status, created_at=po.created_at, total_cost=order_total))

    return PurchaseReport(generated_at=now(), start_date=start_date, end_date=end_date, total_orders=len(items), total_cost=total_cost, items=items)


@router.get("/sales", response_model=SalesReport, dependencies=[Depends(manager_or_admin)])
def sales_report(start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db)):
    query = db.query(SalesOrder).options(joinedload(SalesOrder.items))
    if start_date is not None:
        query = query.filter(SalesOrder.created_at >= start_date)
    if end_date is not None:
        query = query.filter(SalesOrder.created_at <= end_date)
    orders = query.order_by(SalesOrder.created_at.desc()).distinct().all()

    items = []
    total_revenue = Decimal("0")
    for so in orders:
        order_total = sum((i.quantity * i.unit_price for i in so.items), Decimal("0"))
        total_revenue += order_total
        items.append(SalesReportItem(id=so.id, status=so.status, created_at=so.created_at, invoice_number=so.invoice_number, total_amount=order_total))

    return SalesReport(generated_at=now(), start_date=start_date, end_date=end_date, total_orders=len(items), total_revenue=total_revenue, items=items)


@router.get("/inventory", response_model=InventoryReport, dependencies=[Depends(manager_or_admin)])
def inventory_report(start_date: datetime | None = None, end_date: datetime | None = None, db: Session = Depends(get_db)):
    query = db.query(InventoryTransaction)
    if start_date is not None:
        query = query.filter(InventoryTransaction.created_at >= start_date)
    if end_date is not None:
        query = query.filter(InventoryTransaction.created_at <= end_date)
    transactions = query.order_by(InventoryTransaction.created_at.desc()).all()

    summary = InventoryReportSummary(
        total_purchased=sum(t.quantity for t in transactions if t.transaction_type == TransactionType.PURCHASE),
        total_sold=sum(t.quantity for t in transactions if t.transaction_type == TransactionType.SALE),
        total_returned=sum(t.quantity for t in transactions if t.transaction_type == TransactionType.RETURN),
        total_damaged=sum(t.quantity for t in transactions if t.transaction_type == TransactionType.DAMAGE),
    )
    return InventoryReport(
        generated_at=now(), start_date=start_date, end_date=end_date, summary=summary,
        transactions=[InventoryReportItem.model_validate(t, from_attributes=True) for t in transactions],
    )
