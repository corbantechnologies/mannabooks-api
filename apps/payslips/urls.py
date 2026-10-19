from django.urls import path

from . import views

urlpatterns = [
    path("", views.PayslipListView.as_view(), name="payslip-list"),
    path("<uuid:pk>/", views.PayslipDetailView.as_view(), name="payslip-detail"),
]
