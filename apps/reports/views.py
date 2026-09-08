from decimal import Decimal

from django.db.models import F
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsManagerOrAdmin
from apps.catalog.models import Category, Product, Supplier
from apps.core.cache import cached_response
from apps.inventory.models import InventoryTransaction, PurchaseOrder, SalesOrder, TransactionType


class DashboardView(APIView):
    permission_classes = [IsManagerOrAdmin]

    @cached_response("inventory")
    def get(self, request):
        active_products = Product.objects.filter(is_active=True)
        return Response({
            "total_products": active_products.count(),
            "total_categories": Category.objects.filter(is_active=True).count(),
            "total_suppliers": Supplier.objects.filter(is_active=True).count(),
            "total_users": User.objects.filter(is_active=True).count(),
            "total_purchases": PurchaseOrder.objects.count(),
            "total_sales": SalesOrder.objects.count(),
            "low_stock_products": active_products.filter(
                current_stock__gt=0, current_stock__lte=F("low_stock_threshold")
            ).count(),
            "out_of_stock_products": active_products.filter(current_stock__lte=0).count(),
        })


class _DateRangeReportView(APIView):
    permission_classes = [IsManagerOrAdmin]

    def date_range(self, request):
        return request.query_params.get("start_date"), request.query_params.get("end_date")


class ProductReportView(_DateRangeReportView):
    @cached_response("inventory")
    def get(self, request):
        start, end = self.date_range(request)
        qs = Product.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        qs = qs.order_by("-created_at")
        items = [
            {
                "id": p.id, "sku": p.sku, "name": p.name, "category_id": p.category_id, "supplier_id": p.supplier_id,
                "cost_price": p.cost_price, "selling_price": p.selling_price, "current_stock": p.current_stock,
                "low_stock_threshold": p.low_stock_threshold, "is_active": p.is_active,
            }
            for p in qs
        ]
        return Response({
            "generated_at": timezone.now(), "start_date": start, "end_date": end,
            "total_count": len(items), "items": items,
        })


class PurchaseReportView(_DateRangeReportView):
    @cached_response("inventory")
    def get(self, request):
        start, end = self.date_range(request)
        qs = PurchaseOrder.objects.prefetch_related("items")
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        orders = qs.order_by("-created_at")

        items, total_cost = [], Decimal("0")
        for po in orders:
            order_total = sum((i.quantity * i.unit_cost for i in po.items.all()), Decimal("0"))
            total_cost += order_total
            items.append({"id": po.id, "supplier_id": po.supplier_id, "status": po.status, "created_at": po.created_at, "total_cost": order_total})

        return Response({
            "generated_at": timezone.now(), "start_date": start, "end_date": end,
            "total_orders": len(items), "total_cost": total_cost, "items": items,
        })


class SalesReportView(_DateRangeReportView):
    @cached_response("inventory")
    def get(self, request):
        start, end = self.date_range(request)
        qs = SalesOrder.objects.prefetch_related("items")
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        orders = qs.order_by("-created_at")

        items, total_revenue = [], Decimal("0")
        for so in orders:
            order_total = sum((i.quantity * i.unit_price for i in so.items.all()), Decimal("0"))
            total_revenue += order_total
            items.append({"id": so.id, "status": so.status, "created_at": so.created_at, "invoice_number": so.invoice_number, "total_amount": order_total})

        return Response({
            "generated_at": timezone.now(), "start_date": start, "end_date": end,
            "total_orders": len(items), "total_revenue": total_revenue, "items": items,
        })


class InventoryReportView(_DateRangeReportView):
    @cached_response("inventory")
    def get(self, request):
        start, end = self.date_range(request)
        qs = InventoryTransaction.objects.all()
        if start:
            qs = qs.filter(created_at__gte=start)
        if end:
            qs = qs.filter(created_at__lte=end)
        transactions = list(qs.order_by("-created_at"))

        summary = {
            "total_purchased": sum(t.quantity for t in transactions if t.transaction_type == TransactionType.PURCHASE),
            "total_sold": sum(t.quantity for t in transactions if t.transaction_type == TransactionType.SALE),
            "total_returned": sum(t.quantity for t in transactions if t.transaction_type == TransactionType.RETURN),
            "total_damaged": sum(t.quantity for t in transactions if t.transaction_type == TransactionType.DAMAGE),
        }
        items = [
            {
                "id": t.id, "product_id": t.product_id, "quantity": t.quantity, "transaction_type": t.transaction_type,
                "reference_id": t.reference_id, "reason": t.reason, "created_at": t.created_at,
            }
            for t in transactions
        ]
        return Response({
            "generated_at": timezone.now(), "start_date": start, "end_date": end,
            "summary": summary, "transactions": items,
        })
