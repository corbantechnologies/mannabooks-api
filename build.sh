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
# Into the app folder, so it ships in the image; config/settings.py points the running services at the same folder.
# --with-deps adds the system libraries Chromium needs.
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.playwright"
python -m playwright install --with-deps --only-shell chromium
# Fail the build now, rather than PDFs later, if Chromium can't start.
python - <<'PY'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
    page = browser.new_page()
    page.set_content("<p>ok</p>")
    assert page.pdf()[:4] == b"%PDF"
    browser.close()
print("==> Chromium prints PDFs")
PY

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Build finished"
