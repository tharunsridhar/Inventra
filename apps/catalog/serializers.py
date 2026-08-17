from rest_framework import serializers

from apps.catalog.models import Category, Product, Supplier


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name", "description", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "email", "phone", "address", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = [
            "id", "sku", "name", "description", "cost_price", "selling_price", "current_stock",
            "low_stock_threshold", "category", "supplier", "is_active", "created_at",
        ]
        read_only_fields = ["id", "created_at"]
