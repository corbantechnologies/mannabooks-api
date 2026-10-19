# MannaBooks API

Django REST Framework API for MannaBooks, an ERP for Kenyan SMEs. One Django app per model; every
workspace-scoped endpoint lives under `/api/v1/w/<workspace-slug>/`.

## Run it locally

```bash
pipenv install --dev
cp .env.example .env          # then set SECRET_KEY and DATABASE_URL
pipenv run python manage.py migrate
pipenv run python manage.py createsuperuser
pipenv run dev                # http://localhost:8000
```

MannaBooks runs on **PostgreSQL only**, in every environment: `DATABASE_URL` is required and the app
refuses to start without a `postgresql://` URL. Locally, use the public URL of the Railway Postgres.
With `CELERY_TASK_ALWAYS_EAGER=True` background jobs run inline, so Redis is not needed while developing.

- API docs (Swagger): http://localhost:8000/api/v1/docs/
- OpenAPI schema: http://localhost:8000/api/v1/schema/ (the web app generates its types from it)
- Django admin: http://localhost:8000/admin/

## Checks

```bash
pipenv run test               # pytest, on PostgreSQL: creates and drops a test_<db> database
pipenv run lint               # ruff
pipenv run schema             # writes and validates schema.yml
```

## Layout

```
config/            settings, root urls, celery app, wsgi/asgi
apps/
  core/            base models, tenancy, permission catalogue, error shape (no tables)
  accounts/        custom User, sign-in (email, Google), JWT
  workspaces/      the business (tenant) and the caller's context in it
  branches/  roles/  memberships/  invitations/  departments/  employees/  sequences/  auditlogs/
  ledgeraccounts/  chart of accounts (seeded with a Kenyan SME chart)
  journals/        journal entries and the posting engine (services.py)
  fiscalyears/  periods/  currencies/  exchangerates/  taxrates/  openingbalances/
  reports/         trial balance and other read-only reports (no tables)
```

### The posting engine

Everything that reaches the ledger goes through `apps.journals.services`: `post_draft` for manual
entries, `replace_for_source` for records from other modules (it replaces their earlier entries, or
reverses them if their month is closed) and `reverse_entry`. Each call checks that debits equal credits,
that every account is active and that the date is in an open period.

Each app has `models.py`, `serializers.py`, `views.py`, `urls.py`, `admin.py`, plus `services.py`
for business rules, `tasks.py` for Celery jobs and `tests/`. Views are DRF generic views
(`ListCreateAPIView`, `RetrieveUpdateDestroyAPIView`, ...). Workspace views use
`apps.core.tenancy.WorkspaceScopedMixin`, which checks membership and the `module.action`
permission, filters by workspace and writes the audit log.

## Errors

Every error has the same shape:

```json
{"code": "invalid", "message": "Check the highlighted fields.", "errors": {"email": ["..."]}}
```

`code` is one of `invalid`, `not_authenticated`, `permission_denied`, `not_found`, `rule` (a business
rule, HTTP 409), `throttled` or `server_error`.

## Deploy (Railway)

Railway builds with Nixpacks from the Pipfile (Python pinned in `nixpacks.toml`); no Docker.
`railway.json` makes every service run `build.sh` after installing packages (Django checks and
`collectstatic`). Migrations run when the web service starts, because the database isn't reachable
during Railway builds. Create three services from this repo, each with its start command from `Procfile`:

| Service | Start command |
| --- | --- |
| web | `web` line: migrate, then gunicorn |
| worker | `celery -A config worker --loglevel=info` |
| beat | `celery -A config beat --loglevel=info` |

Add the Postgres and Redis plugins and set the variables listed in `.env.example` (with
`DEBUG=False`, a long `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `FRONTEND_URL`,
`CORS_ALLOWED_ORIGINS` and the email settings). Google sign-in stays off until `GOOGLE_SIGNIN_ENABLED=True`
and `GOOGLE_CLIENT_IDS` are set.
