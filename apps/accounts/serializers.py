from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.accounts.models import RoleName, User


class UserReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_active", "created_at"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Anyone can self-register, but they always come in as Employee - only
    an Admin can promote someone via UserViewSet.assign_role. Mirrors
    Inventra's POST /auth/register exactly."""

    password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "email", "password", "full_name"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return User.objects.create_user(role=RoleName.EMPLOYEE, **validated_data)


class UserCreateSerializer(serializers.ModelSerializer):
    """Admin-only user creation, unlike RegisterSerializer - role is settable here."""

    password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])

    class Meta:
        model = User
        fields = ["id", "email", "password", "full_name", "role"]
        read_only_fields = ["id"]

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["full_name", "email"]


class AssignRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=RoleName.choices)


class ResetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(min_length=8, validators=[validate_password])
