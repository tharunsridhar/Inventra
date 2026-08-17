from django.contrib import admin

from apps.inventory.models import (
    InventoryTransaction,
    PurchaseOrder,
    PurchaseOrderItem,
    Return,
    SalesOrder,
    SalesOrderItem,
)


class PurchaseOrderItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0
    autocomplete_fields = ["product"]


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ["id", "supplier", "status", "received_at", "created_by", "created_at"]
    list_filter = ["status"]
    search_fields = ["id__iexact", "supplier__name"]
    autocomplete_fields = ["supplier"]
    readonly_fields = ["id", "created_at", "updated_at", "received_at"]
    inlines = [PurchaseOrderItemInline]


class SalesOrderItemInline(admin.TabularInline):
    model = SalesOrderItem
    extra = 0
    autocomplete_fields = ["product"]


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ["id", "customer_name", "status", "invoice_number", "created_by", "created_at"]
    list_filter = ["status"]
    search_fields = ["id__iexact", "customer_name", "invoice_number"]
    readonly_fields = ["id", "created_at", "updated_at", "invoiced_at", "invoice_number"]
    inlines = [SalesOrderItemInline]


@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ["id", "sales_order", "product", "quantity", "status", "approved_by", "created_at"]
    list_filter = ["status"]
    search_fields = ["id__iexact"]
    autocomplete_fields = ["sales_order", "product"]
    readonly_fields = ["id", "created_at", "approved_by"]


@admin.register(InventoryTransaction)
class InventoryTransactionAdmin(admin.ModelAdmin):
    """Read-only, deliberately: every field is in readonly_fields AND
    add/change/delete permissions are all disabled below. This is the admin
    equivalent of Inventra's transactions.py only ever defining a GET route
    - the immutable-ledger guarantee holds here too, not just in the API."""

    list_display = ["id", "product", "quantity", "transaction_type", "reference_id", "created_by", "created_at"]
    list_filter = ["transaction_type"]
    search_fields = ["id__iexact", "product__name", "product__sku", "reference_id__iexact"]
    readonly_fields = [f.name for f in InventoryTransaction._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
