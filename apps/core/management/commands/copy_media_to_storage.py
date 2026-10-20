"""Copy files saved on the server's disk (the old volume at MEDIA_ROOT) into the configured storage (the bucket).

Run once after setting the bucket variables: `python manage.py copy_media_to_storage`. Files already in the
bucket are skipped, so it is safe to run again. File paths stay the same, so records keep pointing at them.
"""
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Copy uploaded files from MEDIA_ROOT into the configured storage (e.g. the Railway Bucket)."

    def handle(self, *args, **options):
        if not settings.AWS_STORAGE_BUCKET_NAME:
            raise CommandError("No bucket configured: set AWS_STORAGE_BUCKET_NAME and the other AWS_* variables first.")
        root = Path(settings.MEDIA_ROOT)
        if not root.exists():
            self.stdout.write("No local media folder; nothing to copy.")
            return
        copied = skipped = 0
        for path in sorted(p for p in root.rglob("*") if p.is_file()):
            name = path.relative_to(root).as_posix()
            if default_storage.exists(name):
                skipped += 1
                continue
            with path.open("rb") as fh:
                default_storage.save(name, File(fh))
            copied += 1
            self.stdout.write(f"copied {name}")
        self.stdout.write(self.style.SUCCESS(f"Done: {copied} copied, {skipped} already there."))
