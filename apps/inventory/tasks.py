"""Celery tasks for Phase 4. All three are idempotent by construction -
CELERY_TASK_ACKS_LATE means a worker crash mid-task redelivers it, so
"run this twice" must always be safe:
  - generate_invoice_pdf: invoice_number is fixed once a sale completes, so
    regenerating just overwrites the same file with the same content.
  - sweep_low_stock: skips any product that already has an unread alert of
    the same type, so a redelivered run creates nothing new.
  - reconcile_ledger: pure read + notify, never mutates stock, so running
    it twice just re-detects (and re-reports) the same mismatches.
"""

import logging
import os

from celery import shared_task
from django.conf import settings
from django.db.models import Case, F, IntegerField, Sum, When

logger = logging.getLogger(__name__)

_RETRY_KWARGS = {"autoretry_for": (Exception,), "retry_backoff": True, "max_retries": 3}


@shared_task(bind=True, **_RETRY_KWARGS)
def generate_invoice_pdf(self, sales_order_id):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    from apps.inventory.models import SalesOrder, SalesOrderStatus

    so = SalesOrder.objects.prefetch_related("items__product").get(pk=sales_order_id)
    if so.status != SalesOrderStatus.COMPLETED or not so.invoice_number:
        # Not a transient failure - retrying won't make this order completed.
        raise ValueError(f"Sales order {sales_order_id} has no invoice to generate")

    invoices_dir = os.path.join(settings.MEDIA_ROOT, "invoices")
    os.makedirs(invoices_dir, exist_ok=True)
    relative_path = f"invoices/{so.invoice_number}.pdf"
    file_path = os.path.join(settings.MEDIA_ROOT, relative_path)

    c = canvas.Canvas(file_path, pagesize=letter)
    width, height = letter
    y = height - 72
    c.setFont("Helvetica-Bold", 16)
    c.drawString(72, y, f"Invoice {so.invoice_number}")
    c.setFont("Helvetica", 10)
    y -= 24
    c.drawString(72, y, f"Sales order: {so.id}")
    y -= 14
    c.drawString(72, y, f"Invoiced at: {so.invoiced_at}")
    y -= 14
    c.drawString(72, y, f"Customer: {so.customer_name or '-'} ({so.customer_phone or '-'})")
    y -= 28
    c.setFont("Helvetica-Bold", 10)
    c.drawString(72, y, "Product")
    c.drawString(320, y, "Qty")
    c.drawString(380, y, "Unit price")
    c.drawString(470, y, "Line total")
    c.setFont("Helvetica", 10)
    total = 0
    for item in so.items.all():
        y -= 16
        line_total = item.quantity * item.unit_price
        total += line_total
        c.drawString(72, y, item.product.name[:40])
        c.drawString(320, y, str(item.quantity))
        c.drawString(380, y, f"{item.unit_price:.2f}")
        c.drawString(470, y, f"{line_total:.2f}")
    y -= 28
    c.setFont("Helvetica-Bold", 12)
    c.drawString(380, y, f"Total: {total:.2f}")
    c.showPage()
    c.save()

    return {"invoice_number": so.invoice_number, "path": relative_path}


@shared_task(bind=True, **_RETRY_KWARGS)
def sweep_low_stock(self):
    """Celery Beat, every 15 minutes (see CELERY_BEAT_SCHEDULE). Catches
    anything the inline check_and_notify_stock() in apps.inventory.views
    might have missed (e.g. a threshold lowered after the fact) rather than
    relying solely on the at-transaction-time check."""
    from apps.catalog.models import Product
    from apps.notifications.models import Notification, NotificationType
    from apps.notifications.services import notify_admins_and_managers

    candidates = [
        (product, NotificationType.OUT_OF_STOCK, f"{product.name} ({product.sku}) is out of stock")
        for product in Product.objects.filter(is_active=True, current_stock__lte=0)
    ] + [
        (product, NotificationType.LOW_STOCK, f"{product.name} ({product.sku}) is low on stock ({product.current_stock} left)")
        for product in Product.objects.filter(is_active=True, current_stock__gt=0, current_stock__lte=F("low_stock_threshold"))
    ]

    flagged = 0
    for product, ntype, message in candidates:
        already_flagged = Notification.objects.filter(type=ntype, reference_id=product.id, is_read=False).exists()
        if already_flagged:
            continue
        notify_admins_and_managers(ntype, message, product.id)
        flagged += 1

    return {"candidates": len(candidates), "flagged": flagged}


@shared_task(bind=True, **_RETRY_KWARGS)
def reconcile_ledger(self):
    """Celery Beat, nightly (see CELERY_BEAT_SCHEDULE). Read-only: asserts
    current_stock == sum of that product's InventoryTransaction rows
    (PURCHASE/RETURN add, SALE/DAMAGE subtract) and only ever logs +
    notifies on a mismatch - it must never silently "fix" current_stock,
    since a mismatch is itself the signal that something upstream is
    already wrong."""
    from apps.catalog.models import Product
    from apps.inventory.models import InventoryTransaction, TransactionType
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify_admins_and_managers

    signed = (
        InventoryTransaction.objects.annotate(
            signed_quantity=Case(
                When(transaction_type__in=[TransactionType.PURCHASE, TransactionType.RETURN], then=F("quantity")),
                When(transaction_type__in=[TransactionType.SALE, TransactionType.DAMAGE], then=-F("quantity")),
                default=0,
                output_field=IntegerField(),
            )
        )
        .values("product_id")
        .annotate(total=Sum("signed_quantity"))
    )
    ledger_totals = {row["product_id"]: row["total"] for row in signed}

    mismatched = [
        (product.id, product.current_stock, ledger_totals.get(product.id, 0))
        for product in Product.objects.all()
        if product.current_stock != ledger_totals.get(product.id, 0)
    ]

    if mismatched:
        logger.error(
            "Ledger reconciliation found %d mismatched product(s): %s",
            len(mismatched),
            [str(pid) for pid, _, _ in mismatched],
        )
        notify_admins_and_managers(
            NotificationType.RECONCILIATION_MISMATCH,
            f"Ledger reconciliation found {len(mismatched)} product(s) with a stock/ledger mismatch",
        )

    return {
        "checked": Product.objects.count(),
        "mismatched_count": len(mismatched),
        "mismatched_product_ids": [str(pid) for pid, _, _ in mismatched],
    }
