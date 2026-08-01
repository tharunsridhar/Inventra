import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import InventoryTransaction, TransactionType
from app.schemas import InventoryTransactionRead, Page

router = APIRouter(prefix="/inventory-transactions", tags=["inventory-transactions"])

manager_or_admin = require_role("admin", "manager")


# read-only on purpose - no POST/PATCH/DELETE here, transactions never change
# once they're written (that's the whole point of an audit trail)
@router.get("", response_model=Page[InventoryTransactionRead], dependencies=[Depends(manager_or_admin)])
def list_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    product_id: uuid.UUID | None = None,
    transaction_type: TransactionType | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(InventoryTransaction)
    if product_id is not None:
        query = query.filter(InventoryTransaction.product_id == product_id)
    if transaction_type is not None:
        query = query.filter(InventoryTransaction.transaction_type == transaction_type)
    if start_date is not None:
        query = query.filter(InventoryTransaction.created_at >= start_date)
    if end_date is not None:
        query = query.filter(InventoryTransaction.created_at <= end_date)
    total = query.count()
    items = query.order_by(InventoryTransaction.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return Page(items=items, total=total, page=page, page_size=page_size)
