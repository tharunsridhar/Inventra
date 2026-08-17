from django.contrib import admin

from apps.catalog.models import Category, Product, Supplier


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "phone", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "email"]
    readonly_fields = ["id", "created_at", "updated_at"]


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["sku", "name", "category", "supplier", "current_stock", "selling_price", "is_active"]
    list_filter = ["is_active", "category", "supplier"]
    search_fields = ["sku", "name"]
    autocomplete_fields = ["category", "supplier"]
    readonly_fields = ["id", "created_at", "updated_at"]
