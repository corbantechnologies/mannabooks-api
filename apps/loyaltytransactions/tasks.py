from celery import shared_task


@shared_task
def expire_loyalty_points() -> int:
    from .services import expire_due

    return expire_due()
