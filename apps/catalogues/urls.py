from django.urls import path

from . import views

urlpatterns = [
    path("", views.CatalogueListCreateView.as_view(), name="catalogue-list"),
    path("analytics/", views.CatalogueAnalyticsView.as_view(), name="catalogue-analytics"),
    path("<uuid:pk>/", views.CatalogueDetailView.as_view(), name="catalogue-detail"),
    path("<uuid:pk>/send/", views.CatalogueSendView.as_view(), name="catalogue-send"),
    path("<uuid:pk>/pdf/", views.CataloguePdfView.as_view(), name="catalogue-pdf"),
    path("<uuid:pk>/items/", views.CatalogueItemsView.as_view(), name="catalogue-items"),
]
