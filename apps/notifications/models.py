import uuid

from django.conf import settings
from django.db import models


class NotificationType(models.TextChoices):
    LOW_STOCK = "low_stock", "Low stock"
    OUT_OF_STOCK = "out_of_stock", "Out of stock"
    PURCHASE_COMPLETED = "purchase_completed", "Purchase completed"
    SALE_COMPLETED = "sale_completed", "Sale completed"


class Notification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications", db_index=True)
    type = models.CharField(max_length=30, choices=NotificationType.choices)
    message = models.CharField(max_length=1000)
    reference_id = models.UUIDField(null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
