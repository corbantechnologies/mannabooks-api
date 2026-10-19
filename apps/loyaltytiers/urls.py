from django.urls import path

from . import views

urlpatterns = [
    path("", views.LoyaltyTierListCreateView.as_view(), name="loyalty-tier-list"),
    path("<uuid:pk>/", views.LoyaltyTierDetailView.as_view(), name="loyalty-tier-detail"),
]
