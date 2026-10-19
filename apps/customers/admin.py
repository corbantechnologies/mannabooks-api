from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ["number", "name", "workspace", "phone", "kra_pin", "is_active"]
    list_filter = ["is_active", "kind"]
    search_fields = ["name", "number", "email", "phone", "kra_pin", "workspace__name"]
