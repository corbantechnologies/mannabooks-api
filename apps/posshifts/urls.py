from django.urls import path

from . import views

urlpatterns = [
    path("", views.PosShiftListCreateView.as_view(), name="pos-shift-list"),
    path("current/", views.CurrentShiftView.as_view(), name="pos-shift-current"),
    path("<uuid:pk>/", views.PosShiftDetailView.as_view(), name="pos-shift-detail"),
    path("<uuid:pk>/close/", views.CloseShiftView.as_view(), name="pos-shift-close"),
]
