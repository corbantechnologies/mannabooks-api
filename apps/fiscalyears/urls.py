from django.urls import path

from . import views

urlpatterns = [
    path("", views.FiscalYearListCreateView.as_view(), name="fiscalyear-list"),
    path("<uuid:pk>/", views.FiscalYearDetailView.as_view(), name="fiscalyear-detail"),
    path("<uuid:pk>/close/", views.FiscalYearCloseView.as_view(), name="fiscalyear-close"),
    path("<uuid:pk>/reopen/", views.FiscalYearReopenView.as_view(), name="fiscalyear-reopen"),
]
