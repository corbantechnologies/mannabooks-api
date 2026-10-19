from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from . import services
from .serializers import (
    ChangePasswordSerializer,
    GoogleLoginSerializer,
    LoginSerializer,
    LogoutSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    RegisterResultSerializer,
    RegisterSerializer,
    TokenPairSerializer,
    UserSerializer,
)


def token_response(user, status_code=status.HTTP_200_OK):
    return Response({**services.issue_tokens(user), "user": UserSerializer(user).data}, status=status_code)


class AuthThrottleMixin:
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


class RegisterView(AuthThrottleMixin, generics.CreateAPIView):
    serializer_class = RegisterSerializer

    @extend_schema(responses={201: RegisterResultSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        response = token_response(user, status.HTTP_201_CREATED)
        workspace = getattr(user, "created_workspace", None)
        response.data["workspace_slug"] = workspace.slug if workspace else None
        if workspace:
            request.workspace = workspace
            from apps.auditlogs import services as audit

            audit.record(request, "create", workspace)
        return response


class LoginView(AuthThrottleMixin, generics.GenericAPIView):
    serializer_class = LoginSerializer

    @extend_schema(responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return token_response(serializer.validated_data["user"])


class GoogleLoginView(AuthThrottleMixin, generics.GenericAPIView):
    """The web app sends the ID token Google gave it; the API verifies it and signs the user in."""

    serializer_class = GoogleLoginSerializer

    @extend_schema(responses={200: TokenPairSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        claims = services.verify_google_token(serializer.validated_data["id_token"])
        return token_response(services.user_from_google(claims))


class LogoutView(generics.GenericAPIView):
    serializer_class = LogoutSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError:
            pass  # already expired or revoked: the outcome is the same
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_object(self):
        return self.request.user


class ChangePasswordView(generics.GenericAPIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={204: None})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetRequestView(AuthThrottleMixin, generics.GenericAPIView):
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(responses={204: None})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.send_password_reset(serializer.validated_data["email"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(AuthThrottleMixin, generics.GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(responses={204: None})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        services.reset_password(data["uid"], data["token"], data["new_password"])
        return Response(status=status.HTTP_204_NO_CONTENT)
