from django.urls import path

from . import views

urlpatterns = [
    path("catalogues/<str:token>/", views.PublicCatalogueView.as_view(), name="public-catalogue"),
    path("catalogues/<str:token>/quote/", views.PublicQuoteRequestView.as_view(), name="public-catalogue-quote"),
    path("quotes/<str:token>/", views.PublicQuoteView.as_view(), name="public-quote"),
    path("quotes/<str:token>/answer/", views.PublicQuoteAnswerView.as_view(), name="public-quote-answer"),
]
