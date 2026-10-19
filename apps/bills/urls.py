from django.urls import path

from . import views

urlpatterns = [
    path("", views.BillListCreateView.as_view(), name="bill-list"),
    path("<uuid:pk>/", views.BillDetailView.as_view(), name="bill-detail"),
    path("<uuid:pk>/post/", views.BillPostView.as_view(), name="bill-post"),
    path("<uuid:pk>/void/", views.BillVoidView.as_view(), name="bill-void"),
]
