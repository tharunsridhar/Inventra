import uuid

from django.conf import settings
from django.db import models


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=1000, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Supplier(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=50, null=True, blank=True)
    address = models.CharField(max_length=1000, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.name


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.CharField(max_length=100, unique=True, db_index=True)
    name = models.CharField(max_length=255, db_index=True)
    description = models.CharField(max_length=2000, null=True, blank=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)
    # indexed: GET /products?sort_by=price
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    # indexed: GET /products?sort_by=stock and the stock_status filter
    current_stock = models.IntegerField(default=0, db_index=True)
    low_stock_threshold = models.IntegerField(default=0)
    # indexed: GET /products?category_id=...
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products", db_index=True)
    # indexed: GET /products?supplier_id=...
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="products", db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.sku} - {self.name}"
