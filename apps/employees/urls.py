from django.urls import path

from . import views

urlpatterns = [
    path("", views.EmployeeListCreateView.as_view(), name="employee-list"),
    path("<uuid:pk>/", views.EmployeeDetailView.as_view(), name="employee-detail"),
    path("<uuid:pk>/invite/", views.EmployeeInviteView.as_view(), name="employee-invite"),
]
