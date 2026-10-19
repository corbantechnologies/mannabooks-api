from django.contrib import admin

from .models import PosRegister


@admin.register(PosRegister)
class PosRegisterAdmin(admin.ModelAdmin):
    list_display = ["name", "branch", "workspace", "is_active"]
