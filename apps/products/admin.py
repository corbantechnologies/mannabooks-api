from django.contrib import admin

from .models import Product


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "kind", "sale_price", "workspace", "is_active"]
    list_filter = ["kind", "is_active"]
    search_fields = ["name", "code", "workspace__name"]
