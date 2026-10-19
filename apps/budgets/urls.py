from django.urls import path

from . import views

urlpatterns = [
    path("", views.BudgetListCreateView.as_view(), name="budget-list"),
    path("check/", views.BudgetCheckView.as_view(), name="budget-check"),
    path("<uuid:pk>/", views.BudgetDetailView.as_view(), name="budget-detail"),
    path("<uuid:pk>/action/", views.BudgetActionView.as_view(), name="budget-action"),
    path("<uuid:pk>/versus-actual/", views.BudgetVersusActualView.as_view(), name="budget-versus-actual"),
]
