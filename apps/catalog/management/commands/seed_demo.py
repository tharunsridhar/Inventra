"""Deterministic demo-data generator for benchmarking (Phase 0.3) and load
testing (Phase 6). All seeded rows are tagged by naming convention so
--flush can find and remove exactly this command's own output, and nothing
else: categories/suppliers named "Demo ...", products with a "DEMO-" SKU
prefix, users with an "@demo.seed" email domain.

Order generation replays the same stock bookkeeping the real /receive,
/complete, /returns/{id}/approve and /damage endpoints do (increment or
decrement Product.current_stock, write one InventoryTransaction per change)
so the seeded dataset satisfies the same ledger invariant
(current_stock == sum of its transactions) that Phase 4's reconciliation
task checks - a seed that violated it on day one would make that task
untestable against a clean baseline.

random.seed(...) makes the distribution of choices (which product, which
quantity, which status) reproducible across runs. Primary keys are still
real uuid4 values (Django's default=uuid.uuid4 on every model here isn't
affected by random.seed) - determinism applies to the shape of the data,
not to the literal ids.
"""

import random
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import RoleName, User
from apps.catalog.models import Category, Product, Supplier
from apps.inventory.models import (
    InventoryTransaction,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    Return,
    ReturnStatus,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    TransactionType,
)

SEED = 42
DEMO_CATEGORY_PREFIX = "Demo Category"
DEMO_SUPPLIER_PREFIX = "Demo Supplier"
DEMO_SKU_PREFIX = "DEMO-"
DEMO_EMAIL_DOMAIN = "@demo.seed"
NUM_CATEGORIES = 10
NUM_SUPPLIERS = 20
BATCH_SIZE = 500


class Command(BaseCommand):
    help = "Seed a deterministic demo dataset for benchmarking and load testing."

    def add_arguments(self, parser):
        parser.add_argument("--products", type=int, default=500)
        parser.add_argument("--orders", type=int, default=2000)
        parser.add_argument("--flush", action="store_true", help="Delete previously seeded demo data first.")

    def handle(self, *args, **options):
        num_products = options["products"]
        num_orders = options["orders"]

        if options["flush"]:
            self._flush()
        elif Category.objects.filter(name__startswith=DEMO_CATEGORY_PREFIX).exists():
            self.stdout.write(self.style.WARNING("Demo data already present - skipping (pass --flush to reseed)."))
            return

        rng = random.Random(SEED)

        with transaction.atomic():
            categories = self._seed_categories()
            suppliers = self._seed_suppliers()
            users = self._seed_users()
            products = self._seed_products(rng, num_products, categories, suppliers, users)
            self._seed_orders(rng, num_orders, products, users)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(categories)} categories, {len(suppliers)} suppliers, {len(users)} users, "
            f"{len(products)} products, ~{num_orders} orders."
        ))

    # -- flush -----------------------------------------------------------

    def _flush(self):
        demo_products = Product.objects.filter(sku__startswith=DEMO_SKU_PREFIX)
        demo_users = User.objects.filter(email__endswith=DEMO_EMAIL_DOMAIN)

        Return.objects.filter(product__in=demo_products).delete()
        InventoryTransaction.objects.filter(product__in=demo_products).delete()
        # Items cascade with their parent order; items' own product FK is
        # PROTECT (blocks deleting a *product* while an item exists), which
        # doesn't stand in the way of deleting the order/item itself.
        SalesOrder.objects.filter(created_by__in=demo_users).delete()
        PurchaseOrder.objects.filter(created_by__in=demo_users).delete()
        demo_products.delete()
        Supplier.objects.filter(name__startswith=DEMO_SUPPLIER_PREFIX).delete()
        Category.objects.filter(name__startswith=DEMO_CATEGORY_PREFIX).delete()
        demo_users.delete()
        self.stdout.write(self.style.WARNING("Flushed previous demo data."))

    # -- reference data ----------------------------------------------------

    def _seed_categories(self):
        cats = [Category(name=f"{DEMO_CATEGORY_PREFIX} {i}") for i in range(1, NUM_CATEGORIES + 1)]
        return Category.objects.bulk_create(cats)

    def _seed_suppliers(self):
        sups = [
            Supplier(name=f"{DEMO_SUPPLIER_PREFIX} {i}", email=f"demo-supplier-{i}{DEMO_EMAIL_DOMAIN}")
            for i in range(1, NUM_SUPPLIERS + 1)
        ]
        return Supplier.objects.bulk_create(sups)

    def _seed_users(self):
        specs = [
            ("demo-admin", RoleName.ADMIN),
            ("demo-manager-1", RoleName.MANAGER),
            ("demo-manager-2", RoleName.MANAGER),
            ("demo-employee-1", RoleName.EMPLOYEE),
            ("demo-employee-2", RoleName.EMPLOYEE),
            ("demo-employee-3", RoleName.EMPLOYEE),
        ]
        users = []
        for local_part, role in specs:
            email = f"{local_part}{DEMO_EMAIL_DOMAIN}"
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password="demopass123", full_name=local_part, role=role)
            users.append(user)
        return users

    def _seed_products(self, rng, num_products, categories, suppliers, users):
        products = []
        for i in range(1, num_products + 1):
            cost = rng.randint(500, 5000) / 100
            markup = rng.uniform(1.2, 2.5)
            products.append(Product(
                sku=f"{DEMO_SKU_PREFIX}{i:05d}",
                name=f"Demo Product {i}",
                cost_price=round(cost, 2),
                selling_price=round(cost * markup, 2),
                current_stock=rng.randint(50, 500),
                low_stock_threshold=rng.randint(5, 50),
                category=rng.choice(categories),
                supplier=rng.choice(suppliers),
                created_by=rng.choice(users),
            ))
        return Product.objects.bulk_create(products, batch_size=BATCH_SIZE)

    # -- orders --------------------------------------------------------

    def _seed_orders(self, rng, num_orders, products, users):
        managers = [u for u in users if u.role in (RoleName.ADMIN, RoleName.MANAGER)]
        stock = {p.id: p.current_stock for p in products}

        purchase_orders, purchase_items = [], []
        sales_orders, sales_items = [], []
        # Product.current_stock was set directly in _seed_products() with no
        # backing transaction - left as-is, that opening balance would be
        # "magic" stock the ledger can never account for, and Phase 4's
        # reconciliation task (current_stock == sum of its transactions)
        # would flag every single seeded product as a mismatch on day one.
        # A real system has no such thing as stock that didn't come from
        # somewhere, so give each product's starting balance its own
        # PURCHASE transaction instead of leaving it untraced.
        transactions = [
            InventoryTransaction(
                id=uuid.uuid4(), product=p, quantity=p.current_stock, transaction_type=TransactionType.PURCHASE,
                created_by=rng.choice(managers),
            )
            for p in products if p.current_stock > 0
        ]
        completed_sales_orders = []  # (SalesOrder, [SalesOrderItem]) for eligible returns

        for n in range(num_orders):
            if rng.random() < 0.5:
                po, items, txns = self._build_purchase_order(rng, products, managers, stock)
                purchase_orders.append(po)
                purchase_items.extend(items)
                transactions.extend(txns)
            else:
                result = self._build_sales_order(rng, n, products, users, stock)
                if result is None:
                    continue
                so, items, txns = result
                sales_orders.append(so)
                sales_items.extend(items)
                transactions.extend(txns)
                if so.status == SalesOrderStatus.COMPLETED:
                    completed_sales_orders.append((so, items))

        returns, return_txns = self._build_returns(rng, completed_sales_orders, users, stock)
        damage_txns = self._build_damage(rng, products, managers, stock, count=max(1, num_orders // 40))
        transactions.extend(return_txns)
        transactions.extend(damage_txns)

        PurchaseOrder.objects.bulk_create(purchase_orders, batch_size=BATCH_SIZE)
        PurchaseOrderItem.objects.bulk_create(purchase_items, batch_size=BATCH_SIZE)
        SalesOrder.objects.bulk_create(sales_orders, batch_size=BATCH_SIZE)
        SalesOrderItem.objects.bulk_create(sales_items, batch_size=BATCH_SIZE)
        Return.objects.bulk_create(returns, batch_size=BATCH_SIZE)
        InventoryTransaction.objects.bulk_create(transactions, batch_size=BATCH_SIZE)

        for p in products:
            p.current_stock = stock[p.id]
        Product.objects.bulk_update(products, ["current_stock"], batch_size=BATCH_SIZE)

    def _build_purchase_order(self, rng, products, managers, stock):
        supplier_items = rng.sample(products, k=rng.randint(1, 3))
        received = rng.random() < 0.8
        po = PurchaseOrder(
            id=uuid.uuid4(),
            supplier=supplier_items[0].supplier,
            status=PurchaseOrderStatus.RECEIVED if received else PurchaseOrderStatus.ORDERED,
            created_by=rng.choice(managers),
        )
        items, txns = [], []
        for product in supplier_items:
            quantity = rng.randint(5, 100)
            items.append(PurchaseOrderItem(
                id=uuid.uuid4(), purchase_order=po, product=product, quantity=quantity,
                unit_cost=product.cost_price,
            ))
            if received:
                stock[product.id] += quantity
                txns.append(InventoryTransaction(
                    id=uuid.uuid4(), product=product, quantity=quantity, transaction_type=TransactionType.PURCHASE,
                    reference_id=po.id, created_by=po.created_by,
                ))
        if received:
            po.received_at = timezone.now()
        return po, items, txns

    def _build_sales_order(self, rng, n, products, users, stock):
        candidates = [p for p in rng.sample(products, k=min(3, len(products))) if stock[p.id] > 0]
        if not candidates:
            return None
        completed = rng.random() < 0.8
        so = SalesOrder(
            id=uuid.uuid4(),
            status=SalesOrderStatus.COMPLETED if completed else SalesOrderStatus.CREATED,
            customer_name=f"Demo Customer {n}",
            created_by=rng.choice(users),
        )
        items, txns = [], []
        for product in candidates:
            available = stock[product.id]
            quantity = rng.randint(1, min(5, available))
            items.append(SalesOrderItem(
                id=uuid.uuid4(), sales_order=so, product=product, quantity=quantity, unit_price=product.selling_price,
            ))
            if completed:
                stock[product.id] -= quantity
                txns.append(InventoryTransaction(
                    id=uuid.uuid4(), product=product, quantity=quantity, transaction_type=TransactionType.SALE,
                    reference_id=so.id, created_by=so.created_by,
                ))
        if completed:
            so.invoice_number = f"INV-DEMO{n:06d}"
            so.invoiced_at = timezone.now()
        return so, items, txns

    def _build_returns(self, rng, completed_sales_orders, users, stock):
        returns, txns = [], []
        sample_size = min(len(completed_sales_orders), max(1, len(completed_sales_orders) // 20))
        for so, items in rng.sample(completed_sales_orders, k=sample_size) if completed_sales_orders else []:
            item = rng.choice(items)
            quantity = rng.randint(1, item.quantity)
            approved = rng.random() < 0.7
            ret = Return(
                id=uuid.uuid4(), sales_order=so, product=item.product, quantity=quantity,
                reason="Demo return", status=ReturnStatus.APPROVED if approved else ReturnStatus.PENDING,
                created_by=rng.choice(users), approved_by=rng.choice(users) if approved else None,
            )
            returns.append(ret)
            if approved:
                stock[item.product_id] += quantity
                txns.append(InventoryTransaction(
                    id=uuid.uuid4(), product=item.product, quantity=quantity, transaction_type=TransactionType.RETURN,
                    reference_id=ret.id, created_by=ret.created_by,
                ))
        return returns, txns

    def _build_damage(self, rng, products, managers, stock, count):
        txns = []
        candidates = [p for p in products if stock[p.id] > 0]
        for product in rng.sample(candidates, k=min(count, len(candidates))):
            quantity = rng.randint(1, min(5, stock[product.id]))
            stock[product.id] -= quantity
            txns.append(InventoryTransaction(
                id=uuid.uuid4(), product=product, quantity=quantity, transaction_type=TransactionType.DAMAGE,
                created_by=rng.choice(managers), reason="Demo damage write-off",
            ))
        return txns
