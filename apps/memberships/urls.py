from django.urls import path

from . import views

urlpatterns = [
    path("", views.MembershipListView.as_view(), name="membership-list"),
    path("<uuid:pk>/", views.MembershipDetailView.as_view(), name="membership-detail"),
]
