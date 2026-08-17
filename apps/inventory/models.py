import uuid

from django.conf import settings
from django.db import models

from apps.catalog.models import Product, Supplier


class PurchaseOrderStatus(models.TextChoices):
    ORDERED = "ordered", "Ordered"
    RECEIVED = "received", "Received"


class SalesOrderStatus(models.TextChoices):
    CREATED = "created", "Created"
    COMPLETED = "completed", "Completed"


class TransactionType(models.TextChoices):
    PURCHASE = "purchase", "Purchase"
    SALE = "sale", "Sale"
    RETURN = "return", "Return"
    DAMAGE = "damage", "Damage"


class ReturnStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"


class PurchaseOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchase_orders", db_index=True)
    status = models.CharField(
        max_length=20, choices=PurchaseOrderStatus.choices, default=PurchaseOrderStatus.ORDERED, db_index=True
    )
    received_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]


class PurchaseOrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name="items", db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+", db_index=True)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class SalesOrder(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    status = models.CharField(
        max_length=20, choices=SalesOrderStatus.choices, default=SalesOrderStatus.CREATED, db_index=True
    )
    customer_name = models.CharField(max_length=255, null=True, blank=True)
    customer_phone = models.CharField(max_length=50, null=True, blank=True)
    invoice_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    invoiced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]


class SalesOrderItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.CASCADE, related_name="items", db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+", db_index=True)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class InventoryTransaction(models.Model):
    """Every stock change (purchase/sale/return/damage) gets one row here.
    No admin ModelAdmin registers add/change/delete permissions for this
    model (see admin.py) - nothing ever updates or deletes a row, by
    construction, same guarantee as Inventra having no PATCH/DELETE route
    on /inventory-transactions at all."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="transactions", db_index=True)
    quantity = models.IntegerField()
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices, db_index=True)
    reference_id = models.UUIDField(null=True, blank=True)
    reason = models.CharField(max_length=1000, null=True, blank=True)  # only used for damage
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, db_index=True
    )

    class Meta:
        ordering = ["-created_at"]


class Return(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sales_order = models.ForeignKey(SalesOrder, on_delete=models.PROTECT, related_name="returns", db_index=True)
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+", db_index=True)
    quantity = models.PositiveIntegerField()
    reason = models.CharField(max_length=1000)
    status = models.CharField(max_length=20, choices=ReturnStatus.choices, default=ReturnStatus.PENDING, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="approved_returns", db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="filed_returns", db_index=True,
    )

    class Meta:
        ordering = ["-created_at"]
