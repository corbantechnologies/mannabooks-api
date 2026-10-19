from django.db import models

from apps.core.models import WorkspaceModel


class Department(WorkspaceModel):
    """A part of the organisation. Its head is the in-charge of every module the department runs."""

    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, blank=True)
    description = models.CharField(max_length=255, blank=True)
    head = models.ForeignKey(
        "employees.Employee", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )
    modules = models.JSONField(default=list, blank=True, help_text="Module keys this department runs, e.g. inventory")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_department_name_per_workspace")]

    def __str__(self):
        return self.name
