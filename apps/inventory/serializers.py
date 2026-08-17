from rest_framework import serializers

from apps.catalog.models import Product, Supplier
from apps.inventory.models import (
    InventoryTransaction,
    PurchaseOrder,
    PurchaseOrderItem,
    Return,
    SalesOrder,
    SalesOrderItem,
)


class PurchaseOrderItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrderItem
        fields = ["id", "product", "quantity", "unit_cost"]


class PurchaseOrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    unit_cost = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)


class PurchaseOrderReadSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "supplier", "status", "received_at", "items", "created_by", "created_at"]
        read_only_fields = fields


class PurchaseOrderWriteSerializer(serializers.Serializer):
    supplier_id = serializers.UUIDField()
    items = PurchaseOrderItemInputSerializer(many=True)

    def validate_supplier_id(self, value):
        if not Supplier.objects.filter(id=value, is_active=True).exists():
            raise serializers.ValidationError("Supplier not found or inactive")
        return value

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        product_ids = [item["product_id"] for item in value]
        active_ids = set(Product.objects.filter(id__in=product_ids, is_active=True).values_list("id", flat=True))
        missing = set(product_ids) - active_ids
        if missing:
            raise serializers.ValidationError(f"Product(s) not found or inactive: {missing}")
        return value


class SalesOrderItemReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalesOrderItem
        fields = ["id", "product", "quantity", "unit_price"]


class SalesOrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class SalesOrderReadSerializer(serializers.ModelSerializer):
    items = SalesOrderItemReadSerializer(many=True, read_only=True)

    class Meta:
        model = SalesOrder
        fields = [
            "id", "status", "customer_name", "customer_phone", "invoice_number",
            "invoiced_at", "items", "created_by", "created_at",
        ]
        read_only_fields = fields


class SalesOrderWriteSerializer(serializers.Serializer):
    customer_name = serializers.CharField(required=False, allow_null=True)
    customer_phone = serializers.CharField(required=False, allow_null=True)
    items = SalesOrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required")
        product_ids = [item["product_id"] for item in value]
        active_ids = set(Product.objects.filter(id__in=product_ids, is_active=True).values_list("id", flat=True))
        missing = set(product_ids) - active_ids
        if missing:
            raise serializers.ValidationError(f"Product(s) not found or inactive: {missing}")
        return value


class InvoiceSerializer(serializers.Serializer):
    sales_order_id = serializers.UUIDField()
    invoice_number = serializers.CharField()
    invoiced_at = serializers.DateTimeField()
    customer_name = serializers.CharField(allow_null=True)
    customer_phone = serializers.CharField(allow_null=True)
    items = SalesOrderItemReadSerializer(many=True)
    total_amount = serializers.DecimalField(max_digits=12, decimal_places=2)


class ReturnReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Return
        fields = [
            "id", "sales_order", "product", "quantity", "reason", "status",
            "approved_by", "created_by", "created_at",
        ]
        read_only_fields = fields


class ReturnCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Return
        fields = ["sales_order", "product", "quantity", "reason"]


class DamageWriteOffSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(min_length=1, max_length=1000)


class InventoryTransactionReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryTransaction
        fields = [
            "id", "product", "quantity", "transaction_type", "reference_id",
            "reason", "created_by", "created_at",
        ]
        read_only_fields = fields
