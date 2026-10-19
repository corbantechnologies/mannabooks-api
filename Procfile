web: python manage.py migrate --noinput && python manage.py sync_preset_roles && gunicorn config.wsgi --bind 0.0.0.0:$PORT --workers ${WEB_CONCURRENCY:-3} --timeout 60 --access-logfile -
worker: celery -A config worker --loglevel=info --concurrency=${CELERY_CONCURRENCY:-2}
beat: celery -A config beat --loglevel=info
