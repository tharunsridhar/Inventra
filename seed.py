"""Fills the database with some demo data so there's something to look at:
one user per role, a few categories/suppliers, and some products with
different stock levels (including a low-stock one and an out-of-stock one).

Safe to run more than once, it just skips anything that's already there.

    uv run python seed.py
"""

from decimal import Decimal

from app.auth import hash_password
from app.database import SessionLocal, seed_roles
from app.models import Category, Product, Role, Supplier, User

DEMO_USERS = [
    ("admin@inventra.com", "admin123", "Ava Admin", "admin"),
    ("manager@inventra.com", "manager123", "Mona Manager", "manager"),
    ("employee@inventra.com", "employee123", "Eli Employee", "employee"),
]

DEMO_CATEGORIES = ["Laptop", "Keyboard", "Mouse", "SSD", "Monitor"]

DEMO_SUPPLIERS = [
    ("Acme Distributors", "contact@acmedist.com", "9820011111", "12 MG Road, Bengaluru"),
    ("Bluewave Components", "sales@bluewave.com", "9820022222", "45 Anna Salai, Chennai"),
]

# (sku, name, category, supplier index, cost, selling price, stock, low stock threshold)
DEMO_PRODUCTS = [
    ("LAP-001", "ThinkPad X1 Carbon", "Laptop", 0, Decimal("85000.00"), Decimal("104999.00"), 15, 5),
    ("LAP-002", "MacBook Air M2", "Laptop", 1, Decimal("92000.00"), Decimal("114900.00"), 4, 5),
    ("KEY-001", "Mechanical Keyboard RGB", "Keyboard", 0, Decimal("1800.00"), Decimal("2999.00"), 30, 10),
    ("MOU-001", "Wireless Mouse", "Mouse", 0, Decimal("350.00"), Decimal("699.00"), 0, 10),
    ("SSD-001", "NVMe SSD 1TB", "SSD", 1, Decimal("4200.00"), Decimal("5999.00"), 25, 8),
    ("MON-001", "24-inch IPS Monitor", "Monitor", 1, Decimal("8500.00"), Decimal("11999.00"), 2, 5),
]


def main():
    db = SessionLocal()
    try:
        seed_roles(db)

        for email, password, full_name, role_name in DEMO_USERS:
            if db.query(User).filter(User.email == email).first() is not None:
                print(f"user {email} already exists, skipping")
                continue
            role = db.query(Role).filter(Role.name == role_name).first()
            db.add(User(email=email, hashed_password=hash_password(password), full_name=full_name, role_id=role.id))
            print(f"created user {email} ({role_name})")
        db.commit()

        category_ids = {}
        for name in DEMO_CATEGORIES:
            category = db.query(Category).filter(Category.name == name).first()
            if category is None:
                category = Category(name=name)
                db.add(category)
                db.commit()
                db.refresh(category)
                print(f"created category {name}")
            category_ids[name] = category.id

        supplier_ids = []
        for name, email, phone, address in DEMO_SUPPLIERS:
            supplier = db.query(Supplier).filter(Supplier.email == email).first()
            if supplier is None:
                supplier = Supplier(name=name, email=email, phone=phone, address=address)
                db.add(supplier)
                db.commit()
                db.refresh(supplier)
                print(f"created supplier {name}")
            supplier_ids.append(supplier.id)

        for sku, name, category_name, supplier_idx, cost, selling, stock, threshold in DEMO_PRODUCTS:
            if db.query(Product).filter(Product.sku == sku).first() is not None:
                print(f"product {sku} already exists, skipping")
                continue
            db.add(
                Product(
                    sku=sku,
                    name=name,
                    cost_price=cost,
                    selling_price=selling,
                    current_stock=stock,
                    low_stock_threshold=threshold,
                    category_id=category_ids[category_name],
                    supplier_id=supplier_ids[supplier_idx],
                )
            )
            print(f"created product {sku} - {name} (stock={stock})")
        db.commit()

        print("\nDemo credentials:")
        for email, password, _full_name, role_name in DEMO_USERS:
            print(f"  {role_name:9s} {email} / {password}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
