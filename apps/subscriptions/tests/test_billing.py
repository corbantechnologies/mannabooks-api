from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.invoices.tests.test_sales_flow import customer, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def mannabooks(make_user, client_for, settings, monkeypatch):
    """MannaBooks' own workspace, with its paybill connected, as the place subscriptions are paid."""
    from apps.mpesaconnections import daraja
    from apps.mpesaconnections.models import MpesaConnection
    from apps.workspaces.services import create_workspace

    staff = make_user(email="finance@mannabooks.co.ke", full_name="MannaBooks Finance")
    home = create_workspace(staff, name="MannaBooks Ltd", currency="KES")
    res = client_for(staff).put(url(home, "mpesa/connection/"), {"shortcode": "600100", "shortcode_type": "paybill", "consumer_key": "ck",
                                                                 "consumer_secret": "cs", "passkey": "pk", "is_active": True}, format="json")
    assert res.status_code == 200, res.data
    monkeypatch.setattr(daraja, "stk_push", lambda conn, **kw: {"CheckoutRequestID": "ws_CO_BILL", "MerchantRequestID": "m1"})
    settings.PLATFORM_WORKSPACE_SLUG = home.slug
    return MpesaConnection.objects.get(workspace=home)


def role(ws, slug):
    from apps.roles.models import Role

    return str(Role.objects.get(workspace=ws, slug=slug).id)


def hook(token, path, body):
    return APIClient().post(f"/api/v1/hooks/pay/{token}/{path}", body, format="json")


def stk_paid(token, amount, receipt="SBL1PAID01"):
    meta = {"Item": [{"Name": "Amount", "Value": amount}, {"Name": "MpesaReceiptNumber", "Value": receipt},
                     {"Name": "TransactionDate", "Value": 20260101101500}, {"Name": "PhoneNumber", "Value": 254712345678}]}
    return hook(token, "stk/", {"Body": {"stkCallback": {"MerchantRequestID": "m1", "CheckoutRequestID": "ws_CO_BILL", "ResultCode": 0,
                                                          "ResultDesc": "ok", "CallbackMetadata": meta}}})


def test_trial_free_limits_coupon_and_mpesa(workspace, owner, client_for, mannabooks):
    from apps.coupons.models import Coupon
    from apps.plans.models import Plan
    from apps.subscriptions.models import Subscription
    from apps.subscriptions.services import update_all

    api = client_for(owner)
    ctx = api.get(f"/api/v1/w/{workspace.slug}/context/").data["subscription"]
    assert ctx["plan_key"] == "kampuni" and ctx["status"] == "trialing" and ctx["account_number"].startswith("MB")
    billing = api.get(url(workspace, "billing/")).data
    assert [p["key"] for p in billing["plans"]] == ["free", "biashara", "duka", "kampuni"]

    # the free plan: small limits
    Plan.objects.filter(key="free").update(max_documents_month=2)
    assert api.post(url(workspace, "billing/free/")).status_code == 200
    cust = customer(api, workspace)
    for _ in range(2):
        assert api.post(url(workspace, "quotations/"), {"customer_id": cust["id"], "lines": [{"description": "Paint", "unit_price": "100"}]},
                        format="json").status_code == 201
    third = api.post(url(workspace, "quotations/"), {"customer_id": cust["id"], "lines": [{"description": "Paint", "unit_price": "100"}]}, format="json")
    assert third.status_code == 409 and third.data["code"] == "plan_upgrade"
    till = api.post(url(workspace, "pos/registers/"), {"name": "Front till"}, format="json")
    assert till.status_code == 409 and till.data["code"] == "plan_upgrade"  # no point of sale on the free plan
    sales = api.post(url(workspace, "invitations/"), {"email": "sales@example.com", "role_id": role(workspace, "sales")}, format="json")
    assert sales.status_code == 409  # one seat, and the owner has it
    assert api.post(url(workspace, "invitations/"), {"email": "books@example.com", "role_id": role(workspace, "accountant")}, format="json").status_code == 201

    # upgrade with a coupon, paid by M-Pesa prompt
    Coupon.objects.create(code="HALF", percent_off=50, payments=2)
    q = api.post(url(workspace, "billing/quote/"), {"plan": "duka", "cycle": "monthly", "coupon": "half"}, format="json").data
    assert q["list_price"] == "3500.00" and q["amount"] == "1750.00"
    assert api.post(url(workspace, "billing/quote/"), {"plan": "duka", "cycle": "monthly", "coupon": "NOPE"}, format="json").status_code == 409
    paid = api.post(url(workspace, "billing/pay/"), {"plan": "duka", "cycle": "monthly", "coupon": "HALF", "phone": "0712345678"}, format="json")
    assert paid.status_code == 201 and paid.data["status"] == "pending", paid.data
    stk_paid(mannabooks.callback_token, 1750)
    sub = Subscription.objects.get(workspace=workspace)
    assert sub.plan.key == "duka" and sub.status == "active" and sub.coupon.code == "HALF" and sub.coupon_payments_left == 1
    assert sub.paid_until >= timezone.localdate() + timedelta(days=27)
    assert api.get(url(workspace, f"billing/payments/{paid.data['id']}/")).data["status"] == "completed"

    # unpaid: due, then read-only after the grace days; billing and help still work
    sub.paid_until = timezone.localdate() - timedelta(days=1)
    sub.save()
    update_all()
    sub.refresh_from_db()
    assert sub.status == "past_due"
    update_all(timezone.localdate() + timedelta(days=20))
    sub.refresh_from_db()
    assert sub.status == "read_only"
    blocked = api.post(url(workspace, "customers/"), {"name": "New Co"}, format="json")
    assert blocked.status_code == 409 and blocked.data["code"] == "subscription_read_only"
    assert api.get(url(workspace, "customers/")).status_code == 200  # still readable
    assert api.post(url(workspace, "support/"), {"category": "billing", "subject": "Paying", "body": "How do I pay?"}, format="json").status_code == 201

    # a payment straight to the paybill with the account number brings it back
    hook(mannabooks.callback_token, "c2b/confirmation/", {"TransID": "SBL2PAYBILL", "TransAmount": "3500", "BillRefNumber": sub.account_number,
                                                          "MSISDN": "254712345678", "FirstName": "Jane", "TransTime": "20260101101500"})
    sub.refresh_from_db()
    assert sub.status == "active" and api.post(url(workspace, "customers/"), {"name": "New Co"}, format="json").status_code == 201


def test_platform_admin(workspace, owner, make_user, client_for, mannabooks):
    from apps.subscriptions.models import Subscription

    member, staff_user = client_for(owner), make_user(email="ops@mannabooks.co.ke", full_name="Ops Person")
    staff_user.is_staff = True
    staff_user.save()
    admin = client_for(staff_user)
    assert member.get("/api/v1/platform/stats/").status_code == 403
    stats = admin.get("/api/v1/platform/stats/").data
    assert stats["businesses"] >= 2 and stats["trialing"] >= 2
    found = admin.get("/api/v1/platform/businesses/", {"search": "acme"}).data["results"]
    assert found[0]["slug"] == workspace.slug and found[0]["plan_key"] == "kampuni"

    assert admin.post(f"/api/v1/platform/businesses/{workspace.slug}/action/", {"action": "block"}, format="json").status_code == 409  # needs a reason
    admin.post(f"/api/v1/platform/businesses/{workspace.slug}/action/", {"action": "block", "reason": "Unpaid and unreachable"}, format="json")
    assert member.get(url(workspace, "customers/")).status_code == 403
    ctx = member.get(f"/api/v1/w/{workspace.slug}/context/").data
    assert ctx["blocked"] and ctx["blocked_reason"] == "Unpaid and unreachable"
    admin.post(f"/api/v1/platform/businesses/{workspace.slug}/action/", {"action": "unblock"}, format="json")
    assert member.get(url(workspace, "customers/")).status_code == 200

    rec = admin.post(f"/api/v1/platform/businesses/{workspace.slug}/action/", {"action": "record_payment", "plan": "biashara", "cycle": "yearly",
                                                                               "periods": 1, "amount": "15000", "method": "bank", "reference": "EFT-77"},
                     format="json")
    assert rec.status_code == 200 and rec.data["plan_key"] == "biashara" and rec.data["status"] == "active"
    detail = admin.get(f"/api/v1/platform/businesses/{workspace.slug}/").data
    assert detail["payments"][0]["reference"] == "EFT-77" and detail["actions"][0]["action"] == "record_payment"

    # a part payment to the paybill waits for staff
    sub = Subscription.objects.get(workspace=workspace)
    hook(mannabooks.callback_token, "c2b/confirmation/", {"TransID": "SBL3PART", "TransAmount": "500", "BillRefNumber": sub.account_number,
                                                          "MSISDN": "254712345678", "TransTime": "20260101101500"})
    todo = admin.get("/api/v1/platform/payments/", {"reconcile": "true"}).data["results"]
    assert len(todo) == 1 and todo[0]["amount"] == "500.00"
    done = admin.post(f"/api/v1/platform/payments/{todo[0]['id']}/action/", {"action": "fail", "note": "Refunded by M-Pesa reversal"}, format="json")
    assert done.data["status"] == "failed"

    # support: the customer opens a ticket, staff reply and keep a private note
    t = member.post(url(workspace, "support/"), {"category": "problem", "subject": "Can't print", "body": "The invoice print is blank"}, format="json").data
    assert t["number"].startswith("T-")
    admin.post(f"/api/v1/platform/tickets/{t['id']}/reply/", {"body": "Customer on old Chrome", "internal": True}, format="json")
    admin.post(f"/api/v1/platform/tickets/{t['id']}/reply/", {"body": "Please update your browser and try again."}, format="json")
    mine = member.get(url(workspace, f"support/{t['id']}/")).data
    assert [m["body"] for m in mine["messages"]] == ["The invoice print is blank", "Please update your browser and try again."]
    assert mine["status"] == "waiting"
    staff_view = admin.get(f"/api/v1/platform/tickets/{t['id']}/").data
    assert len(staff_view["messages"]) == 3
    assert admin.patch(f"/api/v1/platform/tickets/{t['id']}/", {"status": "resolved", "assign_to_me": True}, format="json").data["assigned_to_name"] == "Ops Person"


def test_full_access_for_a_person(workspace, owner, make_user, client_for):
    from apps.subscriptions.models import Subscription
    from apps.workspaces.services import create_workspace

    staff_user = make_user(email="ops@mannabooks.co.ke", full_name="Ops Person")
    staff_user.is_staff = True
    staff_user.save()
    admin = client_for(staff_user)
    found = admin.get("/api/v1/platform/users/", {"search": owner.email}).data["results"]
    assert found[0]["businesses"] == 1 and not found[0]["full_access"]
    act = f"/api/v1/platform/users/{owner.id}/action/"
    assert admin.post(act, {"action": "grant_full_access"}, format="json").status_code == 409  # needs a reason
    granted = admin.post(act, {"action": "grant_full_access", "note": "Partner accountant"}, format="json")
    assert granted.status_code == 200 and granted.data["full_access"]
    sub = Subscription.objects.get(workspace=workspace)
    assert sub.complimentary and sub.plan.key == "kampuni" and sub.status == "active"
    owner.refresh_from_db()  # full access was given through the API, on a fresh copy of the user
    second = create_workspace(owner, name="Second Biz", currency="KES")  # businesses they start later are covered too
    assert Subscription.objects.get(workspace=second).complimentary
    assert admin.post(act, {"action": "make_staff"}, format="json").status_code == 409  # only a superuser
    admin.post(act, {"action": "revoke_full_access"}, format="json")
    sub.refresh_from_db()
    assert not sub.complimentary and sub.status == "trialing"  # a short trial before billing starts


def test_reminders_and_business_full_access(workspace, owner, make_user, client_for, mailoutbox, django_capture_on_commit_callbacks):
    from apps.subscriptions.models import Subscription
    from apps.subscriptions.services import update_all

    sub = Subscription.objects.get(workspace=workspace)
    today = timezone.localdate()
    with django_capture_on_commit_callbacks(execute=True):
        update_all(sub.trial_ends_on - timedelta(days=7))
        update_all(sub.trial_ends_on - timedelta(days=7))  # the same reminder isn't sent twice
    assert len(mailoutbox) == 1 and "trial ends in 7 days" in mailoutbox[0].subject and mailoutbox[0].to == [owner.email]

    staff_user = make_user(email="ops@mannabooks.co.ke", full_name="Ops Person")
    staff_user.is_staff = True
    staff_user.save()
    admin = client_for(staff_user)
    renewals = admin.get("/api/v1/platform/renewals/", {"days": 40}).data
    assert renewals[0]["slug"] == workspace.slug
    act = f"/api/v1/platform/businesses/{workspace.slug}/action/"
    until = (today + timedelta(days=60)).isoformat()
    free = admin.post(act, {"action": "set_complimentary", "complimentary": True, "plan": "kampuni", "until": until, "note": "Church partner"}, format="json")
    assert free.status_code == 200 and free.data["complimentary"] and free.data["complimentary_until"] == until
    assert admin.post(act, {"action": "send_reminder"}, format="json").status_code == 409  # nothing to remind a free business about
    update_all(today + timedelta(days=61))  # the free period ends by itself
    sub.refresh_from_db()
    assert not sub.complimentary and sub.status == "trialing"
