from django.contrib import admin

from .models import Employee


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ["staff_number", "first_name", "last_name", "workspace", "department", "status"]
    list_filter = ["status"]
    search_fields = ["staff_number", "first_name", "last_name", "email", "workspace__name"]
    raw_id_fields = ["workspace", "department", "branch", "reports_to", "membership", "created_by"]
