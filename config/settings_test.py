"""
Settings for the test suite. Tests run on PostgreSQL: pytest-django creates a separate `test_<name>`
database on the server in DATABASE_URL (or TEST_DATABASE_URL) and drops it afterwards.
"""
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))
os.environ.setdefault("DEBUG", "True")
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-that-is-long-enough-for-hs256")
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

from .settings import *  # noqa: E402,F403

DATABASES["default"]["CONN_MAX_AGE"] = 0  # noqa: F405
MIDDLEWARE = [m for m in MIDDLEWARE if "whitenoise" not in m]  # noqa: F405
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
REST_FRAMEWORK = {**REST_FRAMEWORK, "DEFAULT_THROTTLE_CLASSES": (), "DEFAULT_THROTTLE_RATES": {"anon": None, "auth": None}}  # noqa: F405
STORAGES = {**STORAGES, "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}  # noqa: F405
PDF_ENGINE = "off"  # tests never start Chromium
