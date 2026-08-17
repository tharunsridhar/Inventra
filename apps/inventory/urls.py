from django.urls import path
from rest_framework.routers import DefaultRouter

from apps.inventory.views import (
    DamageWriteOffView,
    InventoryTransactionViewSet,
    PurchaseOrderViewSet,
    ReturnViewSet,
    SalesOrderViewSet,
)

router = DefaultRouter()
router.register("purchase-orders", PurchaseOrderViewSet, basename="purchase-order")
router.register("sales-orders", SalesOrderViewSet, basename="sales-order")
router.register("returns", ReturnViewSet, basename="return")
router.register("inventory-transactions", InventoryTransactionViewSet, basename="inventory-transaction")

urlpatterns = [
    path("damage", DamageWriteOffView.as_view(), name="damage-write-off"),
] + router.urls
