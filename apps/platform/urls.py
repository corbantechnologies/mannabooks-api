from django.urls import path

from . import views

urlpatterns = [
    path("stats/", views.StatsView.as_view(), name="platform-stats"),
    path("businesses/", views.BusinessListView.as_view(), name="platform-businesses"),
    path("businesses/<slug:slug>/", views.BusinessDetailView.as_view(), name="platform-business"),
    path("businesses/<slug:slug>/action/", views.BusinessActionView.as_view(), name="platform-business-action"),
    path("users/", views.UserListView.as_view(), name="platform-users"),
    path("users/<uuid:pk>/action/", views.UserActionView.as_view(), name="platform-user-action"),
    path("plans/", views.PlanListCreateView.as_view(), name="platform-plans"),
    path("plans/<uuid:pk>/", views.PlanDetailView.as_view(), name="platform-plan"),
    path("coupons/", views.CouponListCreateView.as_view(), name="platform-coupons"),
    path("coupons/<uuid:pk>/", views.CouponDetailView.as_view(), name="platform-coupon"),
    path("renewals/", views.RenewalListView.as_view(), name="platform-renewals"),
    path("payments/", views.PaymentListView.as_view(), name="platform-payments"),
    path("payments/<uuid:pk>/action/", views.PaymentActionView.as_view(), name="platform-payment-action"),
    path("tickets/", views.TicketListView.as_view(), name="platform-tickets"),
    path("tickets/<uuid:pk>/", views.TicketDetailView.as_view(), name="platform-ticket"),
    path("tickets/<uuid:pk>/reply/", views.TicketReplyView.as_view(), name="platform-ticket-reply"),
    path("actions/", views.ActionLogView.as_view(), name="platform-actions"),
]
