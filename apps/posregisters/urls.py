from django.urls import path

from . import views

urlpatterns = [
    path("", views.PosRegisterListCreateView.as_view(), name="pos-register-list"),
    path("<uuid:pk>/", views.PosRegisterDetailView.as_view(), name="pos-register-detail"),
]
