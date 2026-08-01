from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_role
from app.database import get_db
from app.models import Category, Product, PurchaseOrder, SalesOrder, Supplier, User
from app.schemas import DashboardRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

manager_or_admin = require_role("admin", "manager")


@router.get("", response_model=DashboardRead, dependencies=[Depends(manager_or_admin)])
def get_dashboard(db: Session = Depends(get_db)):
    low_stock = (
        db.query(Product)
        .filter(Product.is_active.is_(True), Product.current_stock > 0, Product.current_stock <= Product.low_stock_threshold)
        .count()
    )
    out_of_stock = db.query(Product).filter(Product.is_active.is_(True), Product.current_stock <= 0).count()

    return DashboardRead(
        total_products=db.query(Product).filter(Product.is_active.is_(True)).count(),
        total_categories=db.query(Category).filter(Category.is_active.is_(True)).count(),
        total_suppliers=db.query(Supplier).filter(Supplier.is_active.is_(True)).count(),
        total_users=db.query(User).filter(User.is_active.is_(True)).count(),
        total_purchases=db.query(PurchaseOrder).count(),
        total_sales=db.query(SalesOrder).count(),
        low_stock_products=low_stock,
        out_of_stock_products=out_of_stock,
    )
