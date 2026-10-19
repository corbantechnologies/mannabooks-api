from django.urls import path

from . import views

urlpatterns = [
    path("", views.LoyaltyMemberListCreateView.as_view(), name="loyalty-member-list"),
    path("<uuid:pk>/", views.LoyaltyMemberDetailView.as_view(), name="loyalty-member-detail"),
    path("<uuid:pk>/adjust/", views.AdjustPointsView.as_view(), name="loyalty-member-adjust"),
]
