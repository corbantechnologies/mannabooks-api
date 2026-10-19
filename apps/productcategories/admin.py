from django.contrib import admin

from .models import ProductCategory


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "parent", "workspace", "is_active"]
    search_fields = ["name", "workspace__name"]
