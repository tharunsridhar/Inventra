from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdmin
from apps.accounts.serializers import (
    AssignRoleSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    UserCreateSerializer,
    UserReadSerializer,
    UserUpdateSerializer,
)


class RegisterView(generics.CreateAPIView):
    """POST /auth/register - the only unauthenticated write in the app."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(UserReadSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserReadSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ModelViewSet):
    """Admin-only: list/retrieve/create/update, plus the same custom actions
    Inventra exposes (assign-role, reset-password, enable/disable) as extra
    routes via @action - DRF's answer to FastAPI's one-off
    @router.patch("/{id}/role") style endpoints."""

    queryset = User.objects.all()
    permission_classes = [IsAdmin]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action in ("update", "partial_update"):
            return UserUpdateSerializer
        return UserReadSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(UserReadSerializer(serializer.instance).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=kwargs.get("partial", False))
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserReadSerializer(instance).data)

    @action(detail=True, methods=["patch"], url_path="role")
    def assign_role(self, request, pk=None):
        user = self.get_object()
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.role = serializer.validated_data["role"]
        user.save(update_fields=["role"])
        return Response(UserReadSerializer(user).data)

    @action(detail=True, methods=["patch"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self.get_object()
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        return Response(UserReadSerializer(user).data)

    @action(detail=True, methods=["patch"], url_path="enable")
    def enable(self, request, pk=None):
        user = self.get_object()
        user.is_active = True
        user.save(update_fields=["is_active"])
        return Response(UserReadSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        """Soft delete - matches Inventra's disable_user, just flips is_active off."""
        user = self.get_object()
        user.is_active = False
        user.save(update_fields=["is_active"])
        return Response(UserReadSerializer(user).data)
