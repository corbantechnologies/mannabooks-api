"""Sign-in rules: issuing tokens, Google sign-in and password resets."""
from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User


def issue_tokens(user: User) -> dict:
    refresh = RefreshToken.for_user(user)
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def verify_google_token(id_token: str) -> dict:
    """Check a Google ID token's signature, audience and expiry; return its claims."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    if not settings.GOOGLE_SIGNIN_ENABLED or not settings.GOOGLE_CLIENT_IDS:
        raise AuthenticationFailed("Google sign-in is turned off. Sign in with your email and password.")
    try:
        claims = google_id_token.verify_oauth2_token(id_token, google_requests.Request())
    except ValueError as exc:
        raise AuthenticationFailed("The Google sign-in could not be verified.") from exc
    if claims.get("aud") not in settings.GOOGLE_CLIENT_IDS:
        raise AuthenticationFailed("The Google sign-in was issued for another app.")
    if not claims.get("email") or not claims.get("email_verified"):
        raise AuthenticationFailed("Your Google account has no verified email address.")
    return claims


@transaction.atomic
def user_from_google(claims: dict) -> User:
    """Find the user by Google id, then by email (linking the account), or create one."""
    sub, email = claims["sub"], claims["email"].lower()
    user = User.objects.filter(google_sub=sub).first()
    if user is None:
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(
                email=email,
                full_name=claims.get("name") or email.split("@")[0],
                avatar_url=claims.get("picture", ""),
            )
        user.google_sub = sub
    user.email_verified = True
    if not user.avatar_url and claims.get("picture"):
        user.avatar_url = claims["picture"]
    user.save()
    if not user.is_active:
        raise AuthenticationFailed("This account is disabled.")
    return user


def send_password_reset(email: str) -> None:
    """Email a reset link if the address has an account. Silent otherwise, so emails can't be probed."""
    user = User.objects.filter(email=email.strip().lower(), is_active=True).first()
    if user is None:
        return
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"
    send_mail(
        "Reset your MannaBooks password",
        f"Hello {user.full_name},\n\nReset your password here (valid for 3 days):\n{link}\n\n"
        "If you did not ask for this, ignore this email.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
    )


def reset_password(uid: str, token: str, password: str) -> User:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        user = None
    if user is None or not default_token_generator.check_token(user, token):
        raise ValidationError({"token": ["This reset link is invalid or has expired."]})
    user.set_password(password)
    user.save(update_fields=["password"])
    return user
