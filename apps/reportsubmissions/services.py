"""
Work reports. A request opens a round of submissions (one per person) for each due date. Every morning
the next round of recurring requests opens, people are reminded before the due date, and reports not
in by the due date are marked overdue and the requester is told.
"""
import os
from datetime import date, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.employees.models import Employee
from apps.recurringinvoices.services import add_months
from apps.reportrequests.models import ReportRequest

from .models import ReportSubmission

S = ReportSubmission.Status
F = ReportRequest.Frequency
MAX_UPLOAD = 10 * 1024 * 1024
ALLOWED = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".ppt", ".pptx", ".txt", ".jpg", ".jpeg", ".png"}


def employee_of(workspace, user) -> Employee | None:
    return Employee.objects.filter(workspace=workspace, membership__user=user, membership__status="active").first()


def below(manager: Employee) -> list[Employee]:
    """Everyone in the reporting line under `manager`, at any depth."""
    out, frontier, seen = [], [manager.pk], {manager.pk}
    while frontier:
        level = list(Employee.objects.filter(reports_to__in=frontier).exclude(status="exited"))
        frontier = []
        for e in level:
            if e.pk not in seen:
                seen.add(e.pk)
                out.append(e)
                frontier.append(e.pk)
    return out


def askable(workspace, user, membership) -> list[Employee]:
    """The people this user may ask for reports: their reporting line, or anyone for work report managers."""
    me = employee_of(workspace, user)
    if membership.has_perm("workreports.manage"):
        everyone = Employee.objects.filter(workspace=workspace).exclude(status="exited")
        return list(everyone.exclude(pk=me.pk) if me else everyone)
    if me is None:
        return []
    team = below(me)
    headed = Employee.objects.filter(workspace=workspace, department__head=me).exclude(status="exited").exclude(pk=me.pk)
    return list({e.pk: e for e in [*team, *headed]}.values())


def check_file(upload) -> None:
    if upload is None:
        return
    if upload.size > MAX_UPLOAD:
        raise BusinessRuleError("The file is too big. The limit is 10 MB.")
    if os.path.splitext(upload.name)[1].lower() not in ALLOWED:
        raise BusinessRuleError("Upload a PDF, Word, Excel, PowerPoint, CSV, text or image file.")


def period_label(req: ReportRequest, due: date) -> str:
    if req.frequency == F.DAILY:
        return f"{due:%a %d %b %Y}"
    if req.frequency == F.WEEKLY:
        return f"Week to {due:%d %b %Y}"
    if req.frequency == F.MONTHLY:
        return f"{due:%B %Y}"
    return ""


def next_due(req: ReportRequest, due: date) -> date | None:
    if req.frequency == F.DAILY:
        nxt = due + timedelta(days=1)
        while nxt.weekday() >= 5:  # working days only
            nxt += timedelta(days=1)
        return nxt
    if req.frequency == F.WEEKLY:
        return due + timedelta(days=7)
    if req.frequency == F.MONTHLY:
        return add_months(req.first_due_date, _months_between(req.first_due_date, due) + 1, req.first_due_date.day)
    return None


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def _notify(emails: list[str], subject: str, body: str) -> None:
    emails = [e for e in emails if e]
    if not emails:
        return
    from .tasks import send_work_report_email

    transaction.on_commit(lambda: send_work_report_email.delay(subject, body, emails))


def _link(workspace) -> str:
    return f"{settings.FRONTEND_URL}/w/{workspace.slug}/work-reports"


def open_round(req: ReportRequest, due: date) -> int:
    made = 0
    for employee in req.assignees.all():
        _, created = ReportSubmission.objects.get_or_create(
            request=req, employee=employee, due_date=due,
            defaults={"workspace": req.workspace, "created_by": req.created_by, "period_label": period_label(req, due)},
        )
        made += created
    if made:
        _notify([e.email or getattr(getattr(e.membership, "user", None), "email", "") for e in req.assignees.select_related("membership__user")],
                f"Work report due {due:%d %b}: {req.title}",
                f"{req.created_by.full_name if req.created_by else 'Your manager'} asked for: {req.title}, due {due:%A %d %B}.\n\n"
                f"{req.instructions}\n\nSubmit it here: {_link(req.workspace)}")
    return made


@transaction.atomic
def create(workspace, *, user, membership, data: dict, template=None, people=None) -> ReportRequest:
    check_file(template)
    allowed = {e.pk: e for e in askable(workspace, user, membership)}
    audience = data.get("audience", ReportRequest.Audience.TEAM)
    if audience == ReportRequest.Audience.TEAM:
        me = employee_of(workspace, user)
        chosen = below(me) if me else []
    elif audience == ReportRequest.Audience.DEPARTMENT:
        if data.get("department") is None:
            raise BusinessRuleError("Choose the department.")
        chosen = list(Employee.objects.filter(workspace=workspace, department=data["department"]).exclude(status="exited"))
    else:
        chosen = list(people or [])
    me = employee_of(workspace, user)
    chosen = [e for e in chosen if me is None or e.pk != me.pk]
    if not chosen:
        raise BusinessRuleError("Nobody to ask: choose people, or set up who reports to you on their employee records.")
    outside = [e.full_name for e in chosen if e.pk not in allowed]
    if outside:
        raise BusinessRuleError(f"You can only ask people below you in the reporting line. Not: {', '.join(outside[:5])}.")
    if data["first_due_date"] < timezone.localdate():
        raise BusinessRuleError("The first due date has passed.")
    req = ReportRequest.objects.create(workspace=workspace, created_by=user, template=template or "", template_name=getattr(template, "name", "") or "",
                                       **{k: v for k, v in data.items() if k in ("title", "instructions", "audience", "department", "frequency",
                                                                                 "first_due_date", "remind_days_before")})
    req.assignees.set(chosen)
    open_round(req, req.first_due_date)
    return req


def can_review(sub: ReportSubmission, user, membership) -> bool:
    return sub.request.created_by_id == user.id or membership.has_perm("workreports.manage")


@transaction.atomic
def submit(sub: ReportSubmission, *, user, body: str = "", upload=None) -> ReportSubmission:
    sub = ReportSubmission.objects.select_for_update(of=("self",)).select_related("employee__membership", "request").get(pk=sub.pk)
    if sub.employee.membership is None or sub.employee.membership.user_id != user.id:
        raise BusinessRuleError("Only the person asked can submit this report.")
    if sub.status in (S.SUBMITTED, S.ACCEPTED):
        raise BusinessRuleError("This report is already in.")
    check_file(upload)
    if not body.strip() and upload is None and not sub.file:
        raise BusinessRuleError("Write the report or attach a file.")
    sub.body = body
    if upload is not None:
        sub.file, sub.file_name = upload, upload.name[:200]
    today = timezone.localdate()
    sub.status, sub.submitted_at, sub.submitted_late = S.SUBMITTED, timezone.now(), today > sub.due_date
    sub.save()
    requester = sub.request.created_by
    if requester:
        _notify([requester.email], f"Report in: {sub.request.title} from {sub.employee.full_name}",
                f"{sub.employee.full_name} submitted {sub.request.title}" + (" (late)" if sub.submitted_late else "") + f".\n\nReview it: {_link(sub.workspace)}")
    return sub


@transaction.atomic
def review(sub: ReportSubmission, *, user, membership, decision: str, comment: str = "") -> ReportSubmission:
    sub = ReportSubmission.objects.select_for_update(of=("self",)).select_related("request", "employee__membership__user").get(pk=sub.pk)
    if not can_review(sub, user, membership):
        raise BusinessRuleError("Only the person who asked for this report can review it.")
    if sub.status != S.SUBMITTED:
        raise BusinessRuleError("Only a submitted report can be reviewed.")
    if decision == "returned" and not comment.strip():
        raise BusinessRuleError("Say what needs to change.")
    sub.status = S.ACCEPTED if decision == "accepted" else S.RETURNED
    sub.reviewed_by, sub.reviewed_at, sub.review_comment = user, timezone.now(), comment
    sub.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_comment", "updated_at"])
    if sub.status == S.RETURNED:
        u = getattr(sub.employee.membership, "user", None)
        _notify([sub.employee.email or getattr(u, "email", "")], f"Report sent back: {sub.request.title}",
                f"{user.full_name} sent your report back: {comment}\n\nUpdate it here: {_link(sub.workspace)}")
    return sub


def run_due(today: date | None = None) -> dict:
    """Daily: open the next rounds, mark overdue reports, and remind people. Safe to run twice."""
    today = today or timezone.localdate()
    opened = late = reminded = 0
    for req in ReportRequest.objects.filter(status=ReportRequest.Status.ACTIVE).exclude(frequency=F.ONCE).select_related("workspace", "created_by"):
        last = req.submissions.order_by("-due_date").values_list("due_date", flat=True).first() or req.first_due_date
        while last < today:  # the round closed: open the next one
            last = next_due(req, last)
            if last is None:
                break
            with transaction.atomic():
                opened += open_round(req, last)
    overdue = ReportSubmission.objects.filter(status=S.PENDING, due_date__lt=today).select_related("request__created_by", "employee", "workspace")
    for sub in overdue:
        sub.status = S.LATE
        sub.save(update_fields=["status", "updated_at"])
        late += 1
        if sub.request.created_by:
            with transaction.atomic():
                _notify([sub.request.created_by.email], f"Overdue: {sub.request.title} from {sub.employee.full_name}",
                        f"{sub.employee.full_name}'s report was due {sub.due_date:%d %b} and hasn't come in.\n\n{_link(sub.workspace)}")
    for sub in ReportSubmission.objects.filter(status__in=[S.PENDING, S.RETURNED], reminded_on__isnull=True).select_related(
            "request", "employee__membership__user", "workspace"):
        if sub.due_date - timedelta(days=sub.request.remind_days_before) <= today <= sub.due_date:
            u = getattr(sub.employee.membership, "user", None)
            with transaction.atomic():
                _notify([sub.employee.email or getattr(u, "email", "")], f"Reminder: {sub.request.title} is due {sub.due_date:%d %b}",
                        f"Your report \"{sub.request.title}\" is due {sub.due_date:%A %d %B}.\n\n{_link(sub.workspace)}")
            sub.reminded_on = today
            sub.save(update_fields=["reminded_on", "updated_at"])
            reminded += 1
    return {"opened": opened, "late": late, "reminded": reminded}
