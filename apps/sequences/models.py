from django.db import models

from apps.core.models import WorkspaceModel


class Sequence(WorkspaceModel):
    """A per-workspace counter for one kind of document or record, e.g. INV-2026-0001."""

    key = models.SlugField(max_length=40, help_text="What it numbers, e.g. invoice, employee")
    prefix = models.CharField(max_length=20)
    next_number = models.PositiveIntegerField(default=1)
    padding = models.PositiveSmallIntegerField(default=4)
    include_year = models.BooleanField(default=False, help_text="Adds the year and restarts at 1 each year.")
    current_year = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["key"]
        constraints = [models.UniqueConstraint(fields=["workspace", "key"], name="unique_sequence_key_per_workspace")]

    def __str__(self):
        return f"{self.key}: {self.prefix}"

    def format(self, number: int, year: int | None = None) -> str:
        middle = f"{year}-" if self.include_year and year else ""
        return f"{self.prefix}{middle}{number:0{self.padding}d}"
