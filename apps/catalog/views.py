from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from apps.accounts.permissions import IsManagerOrAdmin
from apps.catalog.filters import ProductFilter
from apps.catalog.models import Category, Product, Supplier
from apps.catalog.serializers import CategorySerializer, ProductSerializer, SupplierSerializer
from apps.core.throttling import ScopedByActionThrottleMixin


class _ReadForAllWriteForManagers(ScopedByActionThrottleMixin, viewsets.ModelViewSet):
    """Every authenticated role can read; only Manager/Admin can write -
    the same split Inventra's `manager_or_admin` dependency enforces per
    write route, expressed once here via get_permissions() instead of
    once per endpoint."""

    action_throttle_scopes = {
        "create": "write", "update": "write", "partial_update": "write", "destroy": "write",
    }

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsManagerOrAdmin()]


class CategoryViewSet(_ReadForAllWriteForManagers):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    search_fields = ["name"]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class SupplierViewSet(_ReadForAllWriteForManagers):
    queryset = Supplier.objects.filter(is_active=True)
    serializer_class = SupplierSerializer
    search_fields = ["name"]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])


class ProductViewSet(_ReadForAllWriteForManagers):
    queryset = Product.objects.filter(is_active=True).select_related("category", "supplier")
    serializer_class = ProductSerializer
    filterset_class = ProductFilter
    search_fields = ["name", "sku", "category__name", "supplier__name"]
    ordering_fields = ["name", "selling_price", "current_stock", "created_at"]
    ordering = ["-created_at"]

    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save(update_fields=["is_active"])
