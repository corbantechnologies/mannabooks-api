from celery import shared_task


@shared_task
def send_due_reminders() -> int:
    from .services import run_due

    return run_due()
