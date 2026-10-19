from django.contrib import admin

from .models import ServiceCompletion


@admin.register(ServiceCompletion)
class ServiceCompletionAdmin(admin.ModelAdmin):
    list_display = ["number", "service_order", "completion_date", "rating", "workspace"]
