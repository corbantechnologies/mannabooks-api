from celery import shared_task


@shared_task
def run_due_recurring_invoices() -> int:
    from .services import run_due

    return run_due()
