"""
MannaBooks API settings. Everything environment-specific comes from environment variables
(see .env.example); the defaults are safe for local development only.
"""
import os
from datetime import timedelta
from pathlib import Path

import dj_database_url
from celery.schedules import crontab
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)
SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError("SECRET_KEY must be set when DEBUG is off.")
    SECRET_KEY = "dev-only-insecure-secret-key-change-me"

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    # MannaBooks: one model per app
    "apps.core",
    "apps.accounts",
    "apps.workspaces",
    "apps.branches",
    "apps.roles",
    "apps.memberships",
    "apps.invitations",
    "apps.departments",
    "apps.employees",
    "apps.sequences",
    "apps.auditlogs",
    # Phase 1: accounting core
    "apps.currencies",
    "apps.exchangerates",
    "apps.taxrates",
    "apps.ledgeraccounts",
    "apps.journals",
    "apps.fiscalyears",
    "apps.periods",
    "apps.openingbalances",
    "apps.reports",
    # Phase 2: sales
    "apps.customers",
    "apps.products",
    "apps.productcategories",
    "apps.units",
    "apps.pricelists",
    "apps.quotations",
    "apps.invoices",
    "apps.payments",
    "apps.receipts",
    "apps.creditnotes",
    "apps.suppliers",
    "apps.warehouses",
    "apps.stockmovements",
    "apps.purchaseorders",
    "apps.serviceorders",
    "apps.servicecompletions",
    "apps.goodsreceipts",
    "apps.bills",
    "apps.supplierpayments",
    "apps.paymentvouchers",
    "apps.stocktransfers",
    "apps.stockadjustments",
    "apps.stocktakes",
    "apps.billsofmaterials",
    "apps.productionorders",
    "apps.bankaccounts",
    "apps.expenses",
    "apps.otherincomes",
    "apps.banktransfers",
    "apps.bankstatementlines",
    "apps.reconciliations",
    "apps.statutoryrates",
    "apps.leaverequests",
    "apps.payruns",
    "apps.payslips",
    "apps.costcenters",
    "apps.projects",
    "apps.budgets",
    "apps.approvalrules",
    "apps.approvalrequests",
    "apps.fixedassets",
    "apps.depreciationentries",
    "apps.reportrequests",
    "apps.reportsubmissions",
    "apps.deliverynotes",
    "apps.recurringinvoices",
    "apps.reminders",
    "apps.mpesaconnections",
    "apps.mpesatransactions",
    "apps.posregisters",
    "apps.posshifts",
    "apps.loyaltyprograms",
    "apps.loyaltytiers",
    "apps.loyaltymembers",
    "apps.loyaltytransactions",
    "apps.portallinks",
    "apps.etimsdevices",
    "apps.etimssubmissions",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# PostgreSQL in every environment, including local development and tests.
if not os.environ.get("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL must point to a PostgreSQL database (see .env.example).")
DATABASES = {
    "default": dj_database_url.config(
        conn_max_age=int(os.environ.get("DB_CONN_MAX_AGE", "60")),
        conn_health_checks=True,
    )
}
if DATABASES["default"]["ENGINE"] != "django.db.backends.postgresql":
    raise RuntimeError("MannaBooks runs on PostgreSQL only; DATABASE_URL must start with postgresql://")

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- CORS: the web app calls the API from the browser for interactive screens ---
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", FRONTEND_URL)
CORS_ALLOW_CREDENTIALS = False  # JWT in the Authorization header; no cookies cross-site

# --- Django REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": ("rest_framework.throttling.AnonRateThrottle",),
    "DEFAULT_THROTTLE_RATES": {"anon": "60/min", "auth": "10/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_DAYS", "14"))),
    # Refresh tokens are not rotated: the web app may refresh from several parallel requests at once,
    # and a rotated (blacklisted) token would sign the user out. Sign-out still blacklists the token.
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "UPDATE_LAST_LOGIN": True,
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "MannaBooks API",
    "DESCRIPTION": "ERP for Kenyan SMEs. Workspace-scoped endpoints live under /api/v1/w/{workspace}/.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_NAME_OVERRIDES": {
        "PartyKindEnum": "apps.customers.models.Customer.Kind",
        "MembershipStatusEnum": "apps.memberships.models.Membership.Status",
        "InvitationStatusEnum": "apps.invitations.models.Invitation.Status",
        "EmployeeStatusEnum": "apps.employees.models.Employee.Status",
        "JournalStatusEnum": "apps.journals.models.JournalEntry.Status",
        "OpenClosedStatusEnum": "apps.fiscalyears.models.FiscalYear.Status",
        "OpeningBalanceStatusEnum": "apps.openingbalances.models.OpeningBalance.Status",
        "InvoiceStatusEnum": "apps.invoices.models.Invoice.Status",
        "PaymentStatusEnum": "apps.payments.models.Payment.Status",
        "IssuedVoidStatusEnum": "apps.receipts.models.Receipt.Status",
        "QuotationStatusEnum": "apps.quotations.models.Quotation.Status",
        "EtimsSubmissionStatusEnum": "apps.etimssubmissions.models.EtimsSubmission.Status",
        "BudgetStatusEnum": "apps.budgets.models.Budget.Status",
        "FixedAssetStatusEnum": "apps.fixedassets.models.FixedAsset.Status",
        "ReportSubmissionStatusEnum": "apps.reportsubmissions.models.ReportSubmission.Status",
        "ReportRequestStatusEnum": "apps.reportrequests.models.ReportRequest.Status",
        "ReportFrequencyEnum": "apps.reportrequests.models.ReportRequest.Frequency",
        "ProjectStatusEnum": "apps.projects.models.Project.Status",
        "ApprovalRequestStatusEnum": "apps.approvalrequests.models.ApprovalRequest.Status",
        "ApprovalDocumentTypeEnum": "apps.approvalrules.models.DOCUMENT_TYPES",
    },
}

# --- Google sign-in (the web app sends Google's ID token; the API verifies it). Off until configured. ---
GOOGLE_SIGNIN_ENABLED = env_bool("GOOGLE_SIGNIN_ENABLED", False)
GOOGLE_CLIENT_IDS = env_list("GOOGLE_CLIENT_IDS")

# --- KRA eTIMS ---
# Platform-wide switch. Off until KRA approves MannaBooks as an eTIMS integrator: workspaces can save their
# device details, but no document is sent to KRA and documents show "Signing switched off".
ETIMS_ENABLED = env_bool("ETIMS_ENABLED", False)

# Safaricom Daraja: each workspace uses its own app credentials. Callbacks reach the API at PUBLIC_API_URL.
PUBLIC_API_URL = os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/")
MPESA_SANDBOX_URL = os.environ.get("MPESA_SANDBOX_URL", "https://sandbox.safaricom.co.ke")
MPESA_PRODUCTION_URL = os.environ.get("MPESA_PRODUCTION_URL", "https://api.safaricom.co.ke")
ETIMS_SANDBOX_URL = os.environ.get("ETIMS_SANDBOX_URL", "https://etims-api-sbx.kra.go.ke/etims-api")
ETIMS_PRODUCTION_URL = os.environ.get("ETIMS_PRODUCTION_URL", "https://etims-api.kra.go.ke/etims-api")

# Key for secrets stored in the database (Fernet key: 32 url-safe base64 bytes). Derived from SECRET_KEY if unset.
FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")

# --- Celery: every background and scheduled job runs on Railway with the API ---
CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", DEBUG)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    # Nairobi time (CELERY_TIMEZONE). Each job is safe to run twice.
    "recurring-invoices": {"task": "apps.recurringinvoices.tasks.run_due_recurring_invoices", "schedule": crontab(hour=6, minute=0)},
    "payment-reminders": {"task": "apps.reminders.tasks.send_due_reminders", "schedule": crontab(hour=8, minute=0)},
    "loyalty-expiry": {"task": "apps.loyaltytransactions.tasks.expire_loyalty_points", "schedule": crontab(hour=1, minute=0)},
    "work-reports": {"task": "apps.reportsubmissions.tasks.run_work_reports", "schedule": crontab(hour=7, minute=0)},
}

# --- Email ---
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "MannaBooks <no-reply@mannabooks.co.ke>")

# --- Production hardening ---
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_CONTENT_TYPE_NOSNIFF = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
