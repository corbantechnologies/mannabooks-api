from django.urls import path

from . import views

urlpatterns = [
    path("", views.StatementLineListView.as_view(), name="statement-line-list"),
    path("import/", views.StatementImportView.as_view(), name="statement-import"),
    path("<uuid:pk>/suggestions/", views.SuggestionsView.as_view(), name="statement-line-suggestions"),
    path("<uuid:pk>/action/", views.StatementLineActionView.as_view(), name="statement-line-action"),
]
