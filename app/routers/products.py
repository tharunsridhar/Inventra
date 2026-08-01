import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_role
from app.database import get_db
from app.models import Category, Product, Supplier, User
from app.schemas import Page, ProductCreate, ProductRead, ProductUpdate

router = APIRouter(prefix="/products", tags=["products"])

manager_or_admin = require_role("admin", "manager")

SORT_COLUMNS = {
    "name": Product.name,
    "price": Product.selling_price,
    "stock": Product.current_stock,
    "created_at": Product.created_at,
}


@router.get("", response_model=Page[ProductRead])
def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(default=None),
    category_id: uuid.UUID | None = Query(default=None),
    supplier_id: uuid.UUID | None = Query(default=None),
    stock_status: str | None = Query(default=None, description="in_stock | low_stock | out_of_stock"),
    sort_by: str = Query(default="created_at"),
    sort_order: str = Query(default="desc"),
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Product).filter(Product.is_active.is_(True))

    if search:
        pattern = f"%{search}%"
        query = query.join(Category, Product.category_id == Category.id).join(
            Supplier, Product.supplier_id == Supplier.id
        )
        query = query.filter(
            Product.name.ilike(pattern)
            | Product.sku.ilike(pattern)
            | Category.name.ilike(pattern)
            | Supplier.name.ilike(pattern)
        )

    if category_id is not None:
        query = query.filter(Product.category_id == category_id)
    if supplier_id is not None:
        query = query.filter(Product.supplier_id == supplier_id)

    if stock_status == "out_of_stock":
        query = query.filter(Product.current_stock <= 0)
    elif stock_status == "low_stock":
        query = query.filter(Product.current_stock > 0, Product.current_stock <= Product.low_stock_threshold)
    elif stock_status == "in_stock":
        query = query.filter(Product.current_stock > Product.low_stock_threshold)

    total = query.count()

    column = SORT_COLUMNS.get(sort_by, Product.created_at)
    column = column.asc() if sort_order == "asc" else column.desc()
    items = query.order_by(column).offset((page - 1) * page_size).limit(page_size).all()

    return Page(items=items, total=total, page=page, page_size=page_size)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: uuid.UUID, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, db: Session = Depends(get_db), current_user: User = Depends(manager_or_admin)):
    if db.query(Product).filter(Product.sku == payload.sku).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists")

    category = db.query(Category).filter(Category.id == payload.category_id).first()
    if category is None or not category.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")
    supplier = db.query(Supplier).filter(Supplier.id == payload.supplier_id).first()
    if supplier is None or not supplier.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier not found or inactive")

    product = Product(
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        cost_price=payload.cost_price,
        selling_price=payload.selling_price,
        current_stock=payload.current_stock,
        low_stock_threshold=payload.low_stock_threshold,
        category_id=payload.category_id,
        supplier_id=payload.supplier_id,
        created_by=current_user.id,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.patch("/{product_id}", response_model=ProductRead, dependencies=[Depends(manager_or_admin)])
def update_product(product_id: uuid.UUID, payload: ProductUpdate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if payload.sku is not None and payload.sku != product.sku:
        if db.query(Product).filter(Product.sku == payload.sku).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A product with this SKU already exists")
        product.sku = payload.sku
    if payload.name is not None:
        product.name = payload.name
    if payload.description is not None:
        product.description = payload.description
    if payload.cost_price is not None:
        product.cost_price = payload.cost_price
    if payload.selling_price is not None:
        product.selling_price = payload.selling_price
    if payload.low_stock_threshold is not None:
        product.low_stock_threshold = payload.low_stock_threshold
    if payload.category_id is not None:
        category = db.query(Category).filter(Category.id == payload.category_id).first()
        if category is None or not category.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category not found or inactive")
        product.category_id = payload.category_id
    if payload.supplier_id is not None:
        supplier = db.query(Supplier).filter(Supplier.id == payload.supplier_id).first()
        if supplier is None or not supplier.is_active:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Supplier not found or inactive")
        product.supplier_id = payload.supplier_id

    db.commit()
    db.refresh(product)
    return product


@router.delete("/{product_id}", response_model=ProductRead, dependencies=[Depends(manager_or_admin)])
def delete_product(product_id: uuid.UUID, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.is_active = False
    db.commit()
    db.refresh(product)
    return product
