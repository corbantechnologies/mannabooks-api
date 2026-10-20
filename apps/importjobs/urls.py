from django.urls import path

from . import views

urlpatterns = [
    path("imports/", views.ImportListCreateView.as_view(), name="import-list"),
    path("imports/templates/<str:kind>/", views.TemplateView.as_view(), name="import-template"),
    path("exports/<str:kind>/", views.ExportView.as_view(), name="export"),
]
