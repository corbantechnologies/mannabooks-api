from django.urls import path

from . import views

urlpatterns = [
    path("trial-balance/", views.TrialBalanceView.as_view(), name="report-trial-balance"),
    path("profit-and-loss/", views.ProfitAndLossView.as_view(), name="report-profit-and-loss"),
    path("profit-and-loss/by/", views.ProfitAndLossByDimensionView.as_view(), name="report-profit-and-loss-by"),
    path("balance-sheet/", views.BalanceSheetView.as_view(), name="report-balance-sheet"),
    path("aged/<str:kind>/", views.AgedReportView.as_view(), name="report-aged"),
    path("vat/", views.VatSummaryView.as_view(), name="report-vat"),
    path("by-category/", views.CategoryReportView.as_view(), name="report-by-category"),
    path("glance/", views.GlanceView.as_view(), name="report-glance"),
    path("period/", views.PeriodSummaryView.as_view(), name="report-period"),
]
