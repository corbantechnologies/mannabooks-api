from django.urls import path

from . import views

urlpatterns = [
    path("", views.EtimsDeviceView.as_view(), name="etims-device"),
    path("connect/", views.EtimsConnectView.as_view(), name="etims-connect"),
]
