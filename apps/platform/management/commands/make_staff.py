"""Give someone access to the MannaBooks admin (/admin): python manage.py make_staff person@mannabooks.co.ke [--remove]"""
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User


class Command(BaseCommand):
    help = "Make an existing user MannaBooks staff (platform admin), or remove it with --remove."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--remove", action="store_true")

    def handle(self, email, remove=False, **options):
        user = User.objects.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError(f"No user {email}. They need to sign up first.")
        user.is_staff = not remove
        user.save(update_fields=["is_staff"])
        self.stdout.write(self.style.SUCCESS(f"{user.email} is {'no longer' if remove else 'now'} MannaBooks staff."))
