from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.throttling import ScopedByActionThrottleMixin
from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


class NotificationViewSet(ScopedByActionThrottleMixin, viewsets.ReadOnlyModelViewSet):
    """Per-user, filterable by unread - each user only ever sees their own."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    action_throttle_scopes = {"mark_read": "write"}

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        unread_only = self.request.query_params.get("unread")
        if unread_only is not None and unread_only.lower() == "true":
            qs = qs.filter(is_read=False)
        return qs

    @action(detail=True, methods=["patch"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save(update_fields=["is_read"])
        return Response(NotificationSerializer(notification).data)
