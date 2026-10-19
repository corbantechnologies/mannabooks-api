from django.contrib import admin

from .models import FixedAsset


@admin.register(FixedAsset)
class FixedAssetAdmin(admin.ModelAdmin):
    list_display = ("number", "name", "workspace", "cost", "status")
