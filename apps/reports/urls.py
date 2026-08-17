from django.urls import path

from apps.reports.views import (
    DashboardView,
    InventoryReportView,
    ProductReportView,
    PurchaseReportView,
    SalesReportView,
)

urlpatterns = [
    path("dashboard", DashboardView.as_view(), name="dashboard"),
    path("reports/products", ProductReportView.as_view(), name="report-products"),
    path("reports/purchases", PurchaseReportView.as_view(), name="report-purchases"),
    path("reports/sales", SalesReportView.as_view(), name="report-sales"),
    path("reports/inventory", InventoryReportView.as_view(), name="report-inventory"),
]
