from django.urls import path

from . import views

urlpatterns = [path("", views.LoyaltyProgramView.as_view(), name="loyalty-program")]
