from rest_framework import serializers

from apps.core.fields import WorkspaceRelatedField
from apps.departments.models import Department
from apps.employees.models import Employee
from apps.reportrequests.models import ReportRequest

from .models import ReportSubmission


class ReportRequestSerializer(serializers.ModelSerializer):
    department_id = WorkspaceRelatedField(Department, source="department", allow_null=True, required=False)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)
    people_ids = serializers.ListField(child=serializers.UUIDField(), write_only=True, required=False)
    assignee_names = serializers.SerializerMethodField()
    requested_by_name = serializers.CharField(source="created_by.full_name", read_only=True, default=None)
    has_template = serializers.SerializerMethodField()
    counts = serializers.SerializerMethodField()
    template_file = serializers.FileField(write_only=True, required=False)

    class Meta:
        model = ReportRequest
        fields = ["id", "title", "instructions", "audience", "department_id", "department_name", "people_ids", "assignee_names", "frequency",
                  "first_due_date", "remind_days_before", "status", "requested_by_name", "has_template", "template_name", "template_file", "counts",
                  "created_at"]
        read_only_fields = ["id", "department_name", "assignee_names", "requested_by_name", "has_template", "template_name", "counts", "created_at"]

    def get_assignee_names(self, obj) -> list[str]:
        return [e.full_name for e in obj.assignees.all()]

    def get_has_template(self, obj) -> bool:
        return bool(obj.template)

    def get_counts(self, obj) -> dict[str, int]:
        out = {s: 0 for s in ReportSubmission.Status.values}
        for sub in obj.submissions.all():
            out[sub.status] += 1
        return out


class ReportSubmissionSerializer(serializers.ModelSerializer):
    request_id = serializers.UUIDField(source="request.id", read_only=True)
    title = serializers.CharField(source="request.title", read_only=True)
    instructions = serializers.CharField(source="request.instructions", read_only=True)
    has_template = serializers.SerializerMethodField()
    requested_by_name = serializers.CharField(source="request.created_by.full_name", read_only=True, default=None)
    employee_id = serializers.UUIDField(source="employee.id", read_only=True)
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    has_file = serializers.SerializerMethodField()
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)
    can_submit = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()

    class Meta:
        model = ReportSubmission
        fields = ["id", "request_id", "title", "instructions", "has_template", "requested_by_name", "employee_id", "employee_name", "period_label",
                  "due_date", "status", "body", "has_file", "file_name", "submitted_at", "submitted_late", "reviewed_by_name", "reviewed_at",
                  "review_comment", "can_submit", "can_review", "created_at"]
        read_only_fields = fields

    def get_has_template(self, obj) -> bool:
        return bool(obj.request.template)

    def get_has_file(self, obj) -> bool:
        return bool(obj.file)

    def get_can_submit(self, obj) -> bool:
        request = self.context.get("request")
        m = obj.employee.membership
        return bool(request and m and m.user_id == request.user.id and obj.status in ("pending", "late", "returned"))

    def get_can_review(self, obj) -> bool:
        request = self.context.get("request")
        if not request or obj.status != "submitted":
            return False
        from . import services

        return services.can_review(obj, request.user, request.membership)


class ReportSubmitSerializer(serializers.Serializer):
    body = serializers.CharField(required=False, allow_blank=True, default="")
    file = serializers.FileField(required=False)


class ReviewSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=["accepted", "returned"])
    comment = serializers.CharField(required=False, allow_blank=True, default="")


class PersonSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True, default=None)

    class Meta:
        model = Employee
        fields = ["id", "full_name", "job_title", "department_name"]


class RequestUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportRequest
        fields = ["title", "instructions", "remind_days_before", "status"]
