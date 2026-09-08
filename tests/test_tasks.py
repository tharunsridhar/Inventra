"""Phase 4 Celery tasks. config.settings.test sets
CELERY_TASK_ALWAYS_EAGER=True (see that file) so these run inline with no
broker needed; the transaction.on_commit-gates-dispatch guarantee is tested
separately since it holds regardless of eager/real execution - dispatch
itself never happens if the enclosing transaction rolls back."""

import os

import pytest
from django.db import transaction

from apps.accounts.models import RoleName
from apps.inventory.tasks import generate_invoice_pdf, reconcile_ledger, sweep_low_stock
from apps.notifications.models import Notification, NotificationType
from tests.conftest import _make_user, auth_headers

pytestmark = pytest.mark.django_db


def test_generate_invoice_pdf_writes_a_pdf_for_a_completed_order(api_client, employee_user, product, settings):
    so = api_client.post(
        "/sales-orders/", {"items": [{"product_id": str(product.id), "quantity": 1}]},
        format="json", **auth_headers(employee_user),
    ).json()
    complete = api_client.post(f"/sales-orders/{so['id']}/complete/", **auth_headers(employee_user))
    invoice_number = complete.json()["invoice_number"]

    result = generate_invoice_pdf.delay(so["id"])

    assert result.successful()
    assert result.result["invoice_number"] == invoice_number
    pdf_path = os.path.join(settings.MEDIA_ROOT, result.result["path"])
    assert os.path.exists(pdf_path)
    assert os.path.getsize(pdf_path) > 0


@pytest.mark.django_db(transaction=True)
def test_invoice_endpoint_returns_202_with_a_pollable_task(api_client, employee_user, product):
    # transaction=True: the view dispatches generate_invoice_pdf from
    # inside transaction.on_commit(...), which never fires at all inside
    # the default rolled-back-transaction test isolation (see
    # test_caching.py's identical note).
    so = api_client.post(
        "/sales-orders/", {"items": [{"product_id": str(product.id), "quantity": 1}]},
        format="json", **auth_headers(employee_user),
    ).json()
    api_client.post(f"/sales-orders/{so['id']}/complete/", **auth_headers(employee_user))

    res = api_client.get(f"/sales-orders/{so['id']}/invoice/", **auth_headers(employee_user))
    assert res.status_code == 202
    task_id = res.json()["task_id"]

    status_res = api_client.get(f"/tasks/{task_id}/", **auth_headers(employee_user))
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "SUCCESS"
    assert status_res.json()["result_url"].endswith(".pdf")


def test_sweep_low_stock_is_idempotent(admin_user, manager_user, product):
    product.current_stock = 0
    product.low_stock_threshold = 5
    product.save(update_fields=["current_stock", "low_stock_threshold"])

    first = sweep_low_stock.delay()
    assert first.result["flagged"] == 1
    assert Notification.objects.filter(type=NotificationType.OUT_OF_STOCK, reference_id=product.id).count() == 2  # admin + manager

    second = sweep_low_stock.delay()
    assert second.result["flagged"] == 0  # already-unread alert for this product - no duplicate
    assert Notification.objects.filter(type=NotificationType.OUT_OF_STOCK, reference_id=product.id).count() == 2


def test_sweep_low_stock_flags_again_once_the_existing_alert_is_read(admin_user, product):
    product.current_stock = 0
    product.save(update_fields=["current_stock"])
    sweep_low_stock.delay()

    Notification.objects.filter(reference_id=product.id).update(is_read=True)

    second = sweep_low_stock.delay()
    assert second.result["flagged"] == 1


def test_reconcile_ledger_detects_a_mismatch_without_touching_stock(admin_user, product):
    # The `product` fixture itself is already "corrupted" for this purpose:
    # current_stock=10 with zero backing InventoryTransaction rows.
    stock_before = product.current_stock

    result = reconcile_ledger.delay()

    assert result.result["mismatched_count"] >= 1
    assert str(product.id) in result.result["mismatched_product_ids"]
    assert Notification.objects.filter(type=NotificationType.RECONCILIATION_MISMATCH).exists()

    product.refresh_from_db()
    assert product.current_stock == stock_before, "reconciliation must never silently fix the discrepancy"


def test_reconcile_ledger_reports_clean_when_the_ledger_actually_balances(admin_user, category, supplier):
    from apps.catalog.models import Product
    from apps.inventory.models import InventoryTransaction, TransactionType

    balanced = Product.objects.create(
        sku="BALANCED-001", name="Balanced Product", cost_price="5.00", selling_price="9.00",
        current_stock=7, category=category, supplier=supplier,
    )
    InventoryTransaction.objects.create(product=balanced, quantity=7, transaction_type=TransactionType.PURCHASE)

    result = reconcile_ledger.delay()

    assert str(balanced.id) not in result.result["mismatched_product_ids"]


@pytest.mark.django_db(transaction=True)
def test_task_dispatched_in_a_rolled_back_transaction_never_runs(product):
    _make_user(RoleName.ADMIN)  # a recipient for the notification fan-out

    product.current_stock = 0
    product.save(update_fields=["current_stock"])

    try:
        with transaction.atomic():
            transaction.on_commit(lambda: sweep_low_stock.delay())
            raise RuntimeError("force a rollback after registering the on_commit hook")
    except RuntimeError:
        pass

    assert not Notification.objects.filter(type=NotificationType.OUT_OF_STOCK, reference_id=product.id).exists()

    with transaction.atomic():
        transaction.on_commit(lambda: sweep_low_stock.delay())

    assert Notification.objects.filter(type=NotificationType.OUT_OF_STOCK, reference_id=product.id).exists()
