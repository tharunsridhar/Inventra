import django_filters
from django.db.models import F

from apps.catalog.models import Product


class ProductFilter(django_filters.FilterSet):
    category_id = django_filters.UUIDFilter(field_name="category_id")
    supplier_id = django_filters.UUIDFilter(field_name="supplier_id")
    # stock_status isn't a real column, so a plain field filter can't express
    # it - custom method filters are django-filter's way of doing that,
    # equivalent to the if/elif block Inventra's list_products() has for the
    # same three cases.
    stock_status = django_filters.CharFilter(method="filter_stock_status")

    class Meta:
        model = Product
        fields = ["category_id", "supplier_id"]

    def filter_stock_status(self, queryset, name, value):
        if value == "out_of_stock":
            return queryset.filter(current_stock__lte=0)
        if value == "low_stock":
            return queryset.filter(current_stock__gt=0, current_stock__lte=F("low_stock_threshold"))
        if value == "in_stock":
            return queryset.exclude(current_stock__lte=F("low_stock_threshold"))
        return queryset
