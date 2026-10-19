from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "phone", "avatar_url", "email_verified", "has_password", "date_joined"]
        read_only_fields = ["id", "email", "email_verified", "has_password", "date_joined"]

    def get_has_password(self, obj) -> bool:
        return obj.has_usable_password()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})
    business_name = serializers.CharField(
        write_only=True, required=False, allow_blank=True, max_length=150,
        help_text="If given, a workspace with this name is created and the new user becomes its Owner. "
        "Left out when someone signs up to accept an invitation.",
    )

    class Meta:
        model = User
        fields = ["email", "full_name", "phone", "password", "business_name"]

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("An account with this email already exists. Sign in instead.")
        return value

    def validate(self, attrs):
        validate_password(attrs["password"], User(email=attrs["email"], full_name=attrs.get("full_name", "")))
        return attrs

    def create(self, validated_data):
        from django.db import transaction

        from apps.workspaces.services import create_workspace

        business_name = validated_data.pop("business_name", "").strip()
        with transaction.atomic():
            user = User.objects.create_user(**validated_data)
            user.created_workspace = create_workspace(user, name=business_name) if business_name else None
        return user


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        user = authenticate(self.context.get("request"), email=attrs["email"].strip().lower(), password=attrs["password"])
        if user is None:
            raise serializers.ValidationError("Wrong email or password.")
        attrs["user"] = user
        return attrs


class GoogleLoginSerializer(serializers.Serializer):
    id_token = serializers.CharField()


class TokenPairSerializer(serializers.Serializer):
    """What every sign-in returns."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class RegisterResultSerializer(TokenPairSerializer):
    workspace_slug = serializers.CharField(allow_null=True, help_text="The workspace created from business_name, if any")


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = self.context["request"].user
        if user.has_usable_password() and not user.check_password(attrs.get("current_password") or ""):
            raise serializers.ValidationError({"current_password": ["Your current password is wrong."]})
        validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        validate_password(value)
        return value
