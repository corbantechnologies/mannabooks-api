from django.urls import path

from . import views

urlpatterns = [
    path("levels/", views.StockLevelListView.as_view(), name="stock-levels"),
    path("movements/", views.StockMovementListView.as_view(), name="stock-movements"),
]
