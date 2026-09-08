"""Creates (or resets) the single contended product used by
loadtest/locustfile.py's StockMutator scenario. Separate from seed_demo -
this needs to be re-run before *every* load test run (the whole point is
watching its stock get raced down to zero, or below), not once.
"""

from django.core.management.base import BaseCommand
from django.db.models import Count

from apps.catalog.models import Category, Product, Supplier
from apps.inventory.models import InventoryTransaction, SalesOrder, SalesOrderItem

SKU = "LOADTEST-CONTENDED-001"


class Command(BaseCommand):
    help = "Create or reset the contended product used by the StockMutator load test scenario."

    def add_arguments(self, parser):
        parser.add_argument("--stock", type=int, default=100)

    def handle(self, *args, **options):
        stock = options["stock"]
        category, _ = Category.objects.get_or_create(name="Load Test Category")
        supplier, _ = Supplier.objects.get_or_create(
            name="Load Test Supplier", defaults={"email": "loadtest-supplier@example.com"}
        )
        product, created = Product.objects.get_or_create(
            sku=SKU,
            defaults={
                "name": "Load Test Contended Product", "cost_price": "5.00", "selling_price": "9.00",
                "current_stock": stock, "low_stock_threshold": 0, "category": category, "supplier": supplier,
            },
        )

        # Resetting current_stock alone isn't enough - a prior run's
        # InventoryTransaction/SalesOrder rows for this product would still
        # be sitting there, making "how many sales actually went through"
        # (the load test's whole point) a cumulative count across every run
        # ever done, not a clean per-run measurement. StockMutator only ever
        # creates single-item orders for this one product, so every order
        # touching it belongs to this test and is safe to clear.
        InventoryTransaction.objects.filter(product=product).delete()
        stale_order_ids = list(SalesOrderItem.objects.filter(product=product).values_list("sales_order_id", flat=True))
        SalesOrderItem.objects.filter(product=product).delete()
        # Only delete orders left with no items at all - StockMutator only
        # ever creates single-item orders for this product, so this is
        # normally every order in stale_order_ids, but an order that (for
        # some other reason) also referenced a different product would
        # still have that item and is left alone.
        (
            SalesOrder.objects.filter(id__in=stale_order_ids)
            .annotate(remaining_items=Count("items"))
            .filter(remaining_items=0)
            .delete()
        )

        product.current_stock = stock
        product.is_active = True
        product.save(update_fields=["current_stock", "is_active"])

        self.stdout.write(self.style.SUCCESS(f"{SKU} stock reset to {stock} (created={created}, id={product.id})"))
