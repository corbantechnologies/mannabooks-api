from celery import shared_task


@shared_task
def update_subscriptions():
    from .services import update_all

    return update_all()
