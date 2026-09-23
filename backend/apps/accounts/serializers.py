from __future__ import annotations

from django.contrib.auth import authenticate, password_validation
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "role", "role_display",
            "phone", "job_title", "avatar_url", "timezone_name",
            "is_active", "is_staff", "is_superuser", "last_login",
            "last_seen_at", "date_joined", "signature",
        ]
        read_only_fields = ["id", "last_login", "last_seen_at", "date_joined",
                            "is_staff", "is_superuser"]


class UserCreateSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, style={"input_type": "password"})

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "role", "password", "is_active"]

    def validate_password(self, value: str) -> str:
        password_validation.validate_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class LoginSerializer(TokenObtainPairSerializer):
    """JWT login that also returns the user profile."""

    email = serializers.EmailField(required=False)
    role = serializers.CharField(source="user.role", read_only=True)

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user, context=self.context).data
        return data


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value)
        return value


class ProfileUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone", "job_title", "timezone_name", "signature"]
