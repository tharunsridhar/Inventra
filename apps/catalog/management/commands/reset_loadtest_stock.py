"""Creates (or resets) the single contended product used by
loadtest/locustfile.py's StockMutator scenario. Separate from seed_demo -
this needs to be re-run before *every* load test run (the whole point is
watching its stock get raced down to zero, or below), not once.
"""

from django.core.management.base import BaseCommand

from apps.catalog.models import Category, Product, Supplier

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
        if not created:
            product.current_stock = stock
            product.is_active = True
            product.save(update_fields=["current_stock", "is_active"])

        self.stdout.write(self.style.SUCCESS(f"{SKU} stock reset to {stock} (created={created}, id={product.id})"))
