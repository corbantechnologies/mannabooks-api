from django.urls import path, re_path

from . import views

urlpatterns = [
    path("", views.MpesaConnectionView.as_view(), name="mpesa-connection"),
    re_path(r"^(?P<action>test|register)/$", views.MpesaConnectionActionView.as_view(), name="mpesa-connection-action"),
]
