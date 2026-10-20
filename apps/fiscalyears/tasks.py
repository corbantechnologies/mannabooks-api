from celery import shared_task


@shared_task
def roll_forward_financial_years() -> int:
    from .services import roll_forward_all

    return roll_forward_all()
