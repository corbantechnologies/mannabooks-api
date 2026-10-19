from django.urls import path

from . import views

urlpatterns = [
    path("", views.PeriodListView.as_view(), name="period-list"),
    path("<uuid:pk>/close/", views.PeriodCloseView.as_view(), name="period-close"),
    path("<uuid:pk>/reopen/", views.PeriodReopenView.as_view(), name="period-reopen"),
]
