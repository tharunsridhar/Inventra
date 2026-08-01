from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import InventoryTransaction, Product, TransactionType, User
from app.schemas import DamageWriteOffCreate, InventoryTransactionRead
from app.utils import check_and_notify_stock

router = APIRouter(prefix="/damage", tags=["damage"])

manager_or_admin = require_role("admin", "manager")


@router.post("", response_model=InventoryTransactionRead, status_code=status.HTTP_201_CREATED)
def write_off_damage(payload: DamageWriteOffCreate, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if product is None or not product.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product not found or inactive")
    if product.current_stock < payload.quantity:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot write off {payload.quantity} units — only {product.current_stock} in stock",
        )

    try:
        product.current_stock -= payload.quantity
        transaction = InventoryTransaction(
            product_id=product.id,
            quantity=payload.quantity,
            transaction_type=TransactionType.DAMAGE,
            created_by=current_user.id,
            reason=payload.reason,
        )
        db.add(transaction)
        check_and_notify_stock(db, product)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(transaction)
    return transaction
