from django.urls import path

from . import views

urlpatterns = [
    path("", views.GroupListCreateView.as_view(), name="group-list"),
    path("<uuid:pk>/", views.GroupDetailView.as_view(), name="group-detail"),
    path("<uuid:pk>/companies/", views.AddCompanyView.as_view(), name="group-add-company"),
    path("<uuid:pk>/companies/<slug:workspace>/", views.RemoveCompanyView.as_view(), name="group-remove-company"),
    path("<uuid:pk>/reports/profit-and-loss/", views.ConsolidatedPLView.as_view(), name="group-profit-and-loss"),
    path("<uuid:pk>/reports/balance-sheet/", views.ConsolidatedBSView.as_view(), name="group-balance-sheet"),
    path("<uuid:pk>/intercompany/", views.IntercompanyListCreateView.as_view(), name="group-intercompany"),
    path("<uuid:pk>/intercompany/balances/", views.IntercompanyBalancesView.as_view(), name="group-intercompany-balances"),
    path("<uuid:pk>/intercompany/<uuid:tx>/void/", views.IntercompanyVoidView.as_view(), name="group-intercompany-void"),
]
