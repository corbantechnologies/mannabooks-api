from django.urls import re_path

from . import views

urlpatterns = [
    re_path(r"^(?P<token>[\w-]+)/(?P<hook>stk|c2b/confirmation|c2b/validation)/$", views.SafaricomCallbackView.as_view(), name="mpesa-hook"),
]
