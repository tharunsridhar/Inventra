import time
import uuid

import django_filters
import structlog
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAnyRole, IsManagerOrAdmin
from apps.catalog.models import Product
from apps.core.cache import bump_version
from apps.core.throttling import ScopedByActionThrottleMixin
from apps.inventory.models import (
    InventoryTransaction,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseOrderStatus,
    Return,
    ReturnStatus,
    SalesOrder,
    SalesOrderItem,
    SalesOrderStatus,
    TransactionType,
)
from apps.inventory.serializers import (
    DamageWriteOffSerializer,
    InventoryTransactionReadSerializer,
    PurchaseOrderReadSerializer,
    PurchaseOrderWriteSerializer,
    ReturnCreateSerializer,
    ReturnReadSerializer,
    SalesOrderReadSerializer,
    SalesOrderWriteSerializer,
)
from apps.inventory.tasks import generate_invoice_pdf
from apps.notifications.services import notify, notify_admins_and_managers

logger = structlog.get_logger(__name__)


def check_and_notify_stock(product):
    if product.current_stock <= 0:
        notify_admins_and_managers("out_of_stock", f"{product.name} ({product.sku}) is out of stock", product.id)
    elif product.current_stock <= product.low_stock_threshold:
        notify_admins_and_managers(
            "low_stock", f"{product.name} ({product.sku}) is low on stock ({product.current_stock} left)", product.id
        )


class DateRangeFilterMixin:
    """Common start_date/end_date range filter on created_at, shared by
    purchase orders, sales orders, returns and the transaction ledger -
    each Inventra router repeated this by hand."""

    def filter_date_range(self, queryset):
        start = self.request.query_params.get("start_date")
        end = self.request.query_params.get("end_date")
        if start:
            queryset = queryset.filter(created_at__gte=start)
        if end:
            queryset = queryset.filter(created_at__lte=end)
        return queryset


class PurchaseOrderViewSet(ScopedByActionThrottleMixin, DateRangeFilterMixin, viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.select_related("supplier").prefetch_related("items")
    permission_classes = [IsManagerOrAdmin]
    filterset_fields = ["status"]
    action_throttle_scopes = {
        "create": "write", "update": "write", "partial_update": "write", "destroy": "write",
        "receive": "stock_mutation",
    }

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return PurchaseOrderWriteSerializer
        return PurchaseOrderReadSerializer

    def get_queryset(self):
        return self.filter_date_range(super().get_queryset())

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            po = PurchaseOrder.objects.create(supplier_id=serializer.validated_data["supplier_id"], created_by=request.user)
            PurchaseOrderItem.objects.bulk_create([
                PurchaseOrderItem(purchase_order=po, product_id=item["product_id"], quantity=item["quantity"], unit_cost=item["unit_cost"])
                for item in serializer.validated_data["items"]
            ])
        return Response(PurchaseOrderReadSerializer(po).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        po = self.get_object()
        if po.status != PurchaseOrderStatus.ORDERED:
            return Response({"detail": "Purchase order can no longer be modified once received"}, status=status.HTTP_409_CONFLICT)
        serializer = self.get_serializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            if "supplier_id" in serializer.validated_data:
                po.supplier_id = serializer.validated_data["supplier_id"]
                po.save(update_fields=["supplier_id"])
            if "items" in serializer.validated_data:
                po.items.all().delete()
                PurchaseOrderItem.objects.bulk_create([
                    PurchaseOrderItem(purchase_order=po, product_id=item["product_id"], quantity=item["quantity"], unit_cost=item["unit_cost"])
                    for item in serializer.validated_data["items"]
                ])
        po.refresh_from_db()
        return Response(PurchaseOrderReadSerializer(po).data)

    @action(detail=True, methods=["post"])
    def receive(self, request, pk=None):
        with transaction.atomic():
            # SELECT ... FOR UPDATE on the PO row - two concurrent /receive
            # calls on the same PO can't both read status="ordered" before
            # either commits. Same lock Inventra takes with
            # db.query(PurchaseOrder)...with_for_update(), just spelled with
            # the ORM's select_for_update() instead of raw SQLAlchemy Core.
            lock_wait_start = time.monotonic()
            po = PurchaseOrder.objects.select_for_update().get(pk=pk)
            lock_wait_ms = (time.monotonic() - lock_wait_start) * 1000
            if po.status == PurchaseOrderStatus.RECEIVED:
                logger.info("idempotent_replay_409", action="receive", order_id=str(po.id), actor_id=str(request.user.id), role=request.user.role)
                return Response({"detail": "Purchase order has already been received"}, status=status.HTTP_409_CONFLICT)

            # lock product rows in a fixed order (by id) - if two orders
            # share products, every transaction that touches both always
            # locks them in the same order, so they queue up instead of
            # deadlocking each other
            items = list(po.items.order_by("product_id"))
            product_ids, quantity_delta = [], 0
            for item in items:
                product = Product.objects.select_for_update().get(pk=item.product_id)
                product.current_stock += item.quantity
                product.save(update_fields=["current_stock"])
                InventoryTransaction.objects.create(
                    product=product, quantity=item.quantity, transaction_type=TransactionType.PURCHASE,
                    reference_id=po.id, created_by=request.user,
                )
                check_and_notify_stock(product)
                product_ids.append(str(product.id))
                quantity_delta += item.quantity

            po.status = PurchaseOrderStatus.RECEIVED
            po.received_at = timezone.now()
            po.save(update_fields=["status", "received_at"])
            if po.created_by_id:
                notify(po.created_by_id, "purchase_completed", f"Purchase order {po.id} has been received", po.id)
            transaction.on_commit(lambda: bump_version("inventory"))
            logger.info(
                "stock_mutation", action="receive", order_id=str(po.id), product_ids=product_ids,
                quantity_delta=quantity_delta, actor_id=str(request.user.id), role=request.user.role,
                lock_wait_ms=round(lock_wait_ms, 2),
            )

        po.refresh_from_db()
        return Response(PurchaseOrderReadSerializer(po).data)


class SalesOrderViewSet(ScopedByActionThrottleMixin, DateRangeFilterMixin, viewsets.ModelViewSet):
    queryset = SalesOrder.objects.prefetch_related("items")
    permission_classes = [IsAnyRole]
    filterset_fields = ["status"]
    action_throttle_scopes = {
        "create": "write", "update": "write", "partial_update": "write", "destroy": "write",
        "complete": "stock_mutation",
    }

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update"):
            return SalesOrderWriteSerializer
        return SalesOrderReadSerializer

    def get_queryset(self):
        return self.filter_date_range(super().get_queryset())

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            so = SalesOrder.objects.create(
                customer_name=serializer.validated_data.get("customer_name"),
                customer_phone=serializer.validated_data.get("customer_phone"),
                created_by=request.user,
            )
            # price snapshotted from the product's current selling price at
            # creation time, not looked up again later
            products = {p.id: p for p in Product.objects.filter(id__in=[i["product_id"] for i in serializer.validated_data["items"]])}
            SalesOrderItem.objects.bulk_create([
                SalesOrderItem(sales_order=so, product_id=item["product_id"], quantity=item["quantity"], unit_price=products[item["product_id"]].selling_price)
                for item in serializer.validated_data["items"]
            ])
        return Response(SalesOrderReadSerializer(so).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        so = self.get_object()
        if so.status != SalesOrderStatus.CREATED:
            return Response({"detail": "Sales order can no longer be modified once completed"}, status=status.HTTP_409_CONFLICT)
        serializer = self.get_serializer(data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            if "customer_name" in serializer.validated_data:
                so.customer_name = serializer.validated_data["customer_name"]
            if "customer_phone" in serializer.validated_data:
                so.customer_phone = serializer.validated_data["customer_phone"]
            so.save()
            if "items" in serializer.validated_data:
                so.items.all().delete()
                product_ids = [i["product_id"] for i in serializer.validated_data["items"]]
                products = {p.id: p for p in Product.objects.filter(id__in=product_ids)}
                SalesOrderItem.objects.bulk_create([
                    SalesOrderItem(
                        sales_order=so, product_id=item["product_id"], quantity=item["quantity"],
                        unit_price=products[item["product_id"]].selling_price,
                    )
                    for item in serializer.validated_data["items"]
                ])
        so.refresh_from_db()
        return Response(SalesOrderReadSerializer(so).data)

    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        # Phase 6 kill-switch (see apps.core.checks - impossible to deploy
        # False outside DEBUG). Locking OFF still does a "check"
        # (read-then-compare in Python) but not a real one - two concurrent
        # requests can each read the same pre-deduction current_stock
        # before either writes, which is exactly the oversell window this
        # exists to demonstrate.
        locking = settings.INVENTORY_LOCKING_ENABLED
        with transaction.atomic():
            lock_wait_start = time.monotonic()
            so_qs = SalesOrder.objects.select_for_update() if locking else SalesOrder.objects
            so = so_qs.get(pk=pk)
            lock_wait_ms = (time.monotonic() - lock_wait_start) * 1000
            if so.status == SalesOrderStatus.COMPLETED:
                logger.info("idempotent_replay_409", action="complete", order_id=str(so.id), actor_id=str(request.user.id), role=request.user.role)
                return Response({"detail": "Sales order has already been completed"}, status=status.HTTP_409_CONFLICT)

            items = list(so.items.order_by("product_id"))
            products_by_item = {}
            product_qs = Product.objects.select_for_update() if locking else Product.objects
            # check stock for every line item FIRST - if any one item can't
            # be fulfilled, the whole sale is rejected, nothing gets deducted
            for item in items:
                product = product_qs.get(pk=item.product_id)
                if product.current_stock < item.quantity:
                    return Response(
                        {"detail": f"Insufficient stock for '{product.name}': available {product.current_stock}, requested {item.quantity}"},
                        status=status.HTTP_409_CONFLICT,
                    )
                products_by_item[item.id] = product

            product_ids, quantity_delta = [], 0
            for item in items:
                product = products_by_item[item.id]
                product.current_stock -= item.quantity
                product.save(update_fields=["current_stock"])
                InventoryTransaction.objects.create(
                    product=product, quantity=item.quantity, transaction_type=TransactionType.SALE,
                    reference_id=so.id, created_by=request.user,
                )
                check_and_notify_stock(product)
                product_ids.append(str(product.id))
                quantity_delta -= item.quantity

            so.status = SalesOrderStatus.COMPLETED
            so.invoice_number = f"INV-{uuid.uuid4().hex[:10].upper()}"
            so.invoiced_at = timezone.now()
            so.save(update_fields=["status", "invoice_number", "invoiced_at"])
            if so.created_by_id:
                notify(so.created_by_id, "sale_completed", f"Sales order {so.id} has been completed", so.id)
            transaction.on_commit(lambda: bump_version("inventory"))
            logger.info(
                "stock_mutation", action="complete", order_id=str(so.id), product_ids=product_ids,
                quantity_delta=quantity_delta, actor_id=str(request.user.id), role=request.user.role,
                lock_wait_ms=round(lock_wait_ms, 2),
            )

        so.refresh_from_db()
        return Response(SalesOrderReadSerializer(so).data)

    @action(detail=True, methods=["get"])
    def invoice(self, request, pk=None):
        """Generates the invoice PDF asynchronously - was synchronous, now
        returns 202 + a task id immediately and GET /tasks/{id}/ reports
        progress and (once ready) a result_url for the PDF."""
        so = self.get_object()
        if so.status != SalesOrderStatus.COMPLETED or not so.invoice_number:
            return Response({"detail": "Invoice is not available until the sales order is completed"}, status=status.HTTP_404_NOT_FOUND)

        task_id = str(uuid.uuid4())
        # Carries this request's id into the worker's own logs (see
        # apps.core.celery_signals) so one id traces web -> queue -> worker.
        headers = {"request_id": getattr(request, "request_id", None)}
        with transaction.atomic():
            transaction.on_commit(
                lambda: generate_invoice_pdf.apply_async(args=[str(so.id)], task_id=task_id, headers=headers)
            )
        return Response(
            {"task_id": task_id, "status_url": f"/tasks/{task_id}/"},
            status=status.HTTP_202_ACCEPTED,
        )


class ReturnViewSet(ScopedByActionThrottleMixin, viewsets.ModelViewSet):
    queryset = Return.objects.all()
    permission_classes = [IsManagerOrAdmin]
    action_throttle_scopes = {
        "create": "write", "update": "write", "partial_update": "write", "destroy": "write",
        "approve": "stock_mutation",
    }

    def get_serializer_class(self):
        return ReturnCreateSerializer if self.action == "create" else ReturnReadSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs

    def create(self, request, *args, **kwargs):
        with transaction.atomic():
            # lock the sales order so two concurrent return requests against
            # it can't both compute the same "remaining reservable quantity"
            # and both pass
            so = SalesOrder.objects.select_for_update().get(pk=request.data.get("sales_order"))
            if so.status != SalesOrderStatus.COMPLETED:
                return Response({"detail": "Returns can only be filed against a completed sales order"}, status=status.HTTP_400_BAD_REQUEST)

            product_id = request.data.get("product")
            quantity = int(request.data.get("quantity", 0))
            sold_quantity = sum(i.quantity for i in so.items.filter(product_id=product_id))
            if sold_quantity == 0:
                return Response({"detail": "This product was not part of the original sales order"}, status=status.HTTP_400_BAD_REQUEST)

            already_reserved = sum(
                r.quantity for r in Return.objects.filter(
                    sales_order=so, product_id=product_id, status__in=[ReturnStatus.PENDING, ReturnStatus.APPROVED]
                )
            )
            remaining = sold_quantity - already_reserved
            if quantity > remaining:
                return Response({"detail": f"Return quantity exceeds remaining returnable quantity ({remaining})"}, status=status.HTTP_400_BAD_REQUEST)

            ret = Return.objects.create(
                sales_order=so, product_id=product_id, quantity=quantity,
                reason=request.data.get("reason", ""), created_by=request.user,
            )
        return Response(ReturnReadSerializer(ret).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"])
    def approve(self, request, pk=None):
        with transaction.atomic():
            lock_wait_start = time.monotonic()
            ret = Return.objects.select_for_update().get(pk=pk)
            lock_wait_ms = (time.monotonic() - lock_wait_start) * 1000
            if ret.status == ReturnStatus.APPROVED:
                logger.info("idempotent_replay_409", action="approve", order_id=str(ret.id), actor_id=str(request.user.id), role=request.user.role)
                return Response({"detail": "Return has already been approved"}, status=status.HTTP_409_CONFLICT)

            product = Product.objects.select_for_update().get(pk=ret.product_id)
            product.current_stock += ret.quantity
            product.save(update_fields=["current_stock"])
            InventoryTransaction.objects.create(
                product=product, quantity=ret.quantity, transaction_type=TransactionType.RETURN,
                reference_id=ret.id, created_by=request.user,
            )
            ret.status = ReturnStatus.APPROVED
            ret.approved_by = request.user
            ret.save(update_fields=["status", "approved_by"])
            transaction.on_commit(lambda: bump_version("inventory"))
            logger.info(
                "stock_mutation", action="approve", order_id=str(ret.id), product_ids=[str(product.id)],
                quantity_delta=ret.quantity, actor_id=str(request.user.id), role=request.user.role,
                lock_wait_ms=round(lock_wait_ms, 2),
            )

        ret.refresh_from_db()
        return Response(ReturnReadSerializer(ret).data)


class DamageWriteOffView(APIView):
    permission_classes = [IsManagerOrAdmin]
    throttle_scope = "stock_mutation"

    def post(self, request):
        serializer = DamageWriteOffSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            # lock the product row so a concurrent write-off (or a sale
            # racing this write-off) can't both read the same current_stock
            lock_wait_start = time.monotonic()
            product = Product.objects.select_for_update().filter(pk=data["product_id"], is_active=True).first()
            lock_wait_ms = (time.monotonic() - lock_wait_start) * 1000
            if product is None:
                return Response({"detail": "Product not found or inactive"}, status=status.HTTP_400_BAD_REQUEST)
            if product.current_stock < data["quantity"]:
                return Response(
                    {"detail": f"Cannot write off {data['quantity']} units - only {product.current_stock} in stock"},
                    status=status.HTTP_409_CONFLICT,
                )
            product.current_stock -= data["quantity"]
            product.save(update_fields=["current_stock"])
            txn = InventoryTransaction.objects.create(
                product=product, quantity=data["quantity"], transaction_type=TransactionType.DAMAGE,
                created_by=request.user, reason=data["reason"],
            )
            check_and_notify_stock(product)
            transaction.on_commit(lambda: bump_version("inventory"))
            logger.info(
                "stock_mutation", action="damage", order_id=str(txn.id), product_ids=[str(product.id)],
                quantity_delta=-data["quantity"], actor_id=str(request.user.id), role=request.user.role,
                lock_wait_ms=round(lock_wait_ms, 2),
            )

        return Response(InventoryTransactionReadSerializer(txn).data, status=status.HTTP_201_CREATED)


class InventoryTransactionFilter(django_filters.FilterSet):
    product_id = django_filters.UUIDFilter(field_name="product_id")
    transaction_type = django_filters.CharFilter(field_name="transaction_type")

    class Meta:
        model = InventoryTransaction
        fields = ["product_id", "transaction_type"]


class InventoryTransactionViewSet(DateRangeFilterMixin, viewsets.ReadOnlyModelViewSet):
    """Read-only on purpose - no create/update/delete routes exist here at
    all, so the ledger can't be edited or erased once written. That's
    enforced by which router this ViewSet is registered under (list/retrieve
    only), the same way Inventra's transactions.py only ever defines a GET."""

    queryset = InventoryTransaction.objects.select_related("product")
    serializer_class = InventoryTransactionReadSerializer
    permission_classes = [IsManagerOrAdmin]
    filterset_class = InventoryTransactionFilter
    throttle_scope = "read"

    def get_queryset(self):
        return self.filter_date_range(super().get_queryset())
