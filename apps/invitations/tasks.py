from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_invitation_email(self, invitation_id: str) -> None:
    from .models import Invitation

    invitation = Invitation.objects.select_related("workspace", "role", "created_by").filter(pk=invitation_id).first()
    if invitation is None or invitation.status != Invitation.Status.PENDING:
        return
    inviter = invitation.created_by.full_name if invitation.created_by else "Your team"
    try:
        send_mail(
            f"{inviter} invited you to {invitation.workspace.name} on MannaBooks",
            f"Hello,\n\n{inviter} invited you to join {invitation.workspace.name} on MannaBooks "
            f"as {invitation.role.name}.\n\nAccept the invitation here (valid for 7 days):\n{invitation.link}\n",
            settings.DEFAULT_FROM_EMAIL,
            [invitation.email],
        )
    except Exception as exc:  # network or provider error: try again later
        raise self.retry(exc=exc) from exc
