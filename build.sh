#!/usr/bin/env bash
# Railway build step (set as the build command in railway.json). Nixpacks has already installed the
# Pipfile packages; this prepares everything that does not need the database.
# Migrations run when the web service starts (Procfile), because the database is not reachable
# from Railway's build environment.
set -o errexit
set -o pipefail

echo "==> Checking Django configuration"
python manage.py check --deploy --fail-level ERROR

echo "==> Installing Chromium for PDF downloads (Playwright)"
# The browser goes inside the app folder (PLAYWRIGHT_BROWSERS_PATH, set in nixpacks.toml) so it ships with the build;
# --with-deps adds the system libraries Chromium needs.
python -m playwright install --with-deps --only-shell chromium

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Build finished"
