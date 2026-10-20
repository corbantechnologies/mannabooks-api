import pytest

from apps.invoices.tests.test_sales_flow import customer, draft_invoice, url

pytestmark = pytest.mark.django_db


@pytest.fixture
def ws(workspace):
    workspace.vat_registered = True
    workspace.kra_pin = "P051234567X"
    workspace.save()
    return workspace


@pytest.fixture
def api(ws, owner, client_for):
    return client_for(owner)


@pytest.fixture
def day(ws):
    from apps.periods.models import AccountingPeriod

    return AccountingPeriod.objects.filter(workspace=ws).order_by("start_date").first().start_date.isoformat()


def test_email_an_invoice_with_link_and_payment_options(api, ws, day, mailoutbox, django_capture_on_commit_callbacks):
    cust = customer(api, ws, email="accounts@baraka.co.ke")
    inv = draft_invoice(api, ws, cust, day).data
    doc = {"document_type": "invoice", "object_id": inv["id"]}
    early = api.post(url(ws, "document-emails/"), {**doc, "to": "a@b.co", "subject": "x"}, format="json")
    assert early.status_code == 409  # a draft isn't sent
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    api.post(url(ws, "payment-options/"), {"kind": "mpesa_paybill", "number": "247247"}, format="json")
    draft = api.get(url(ws, "document-emails/draft/"), doc).data
    assert draft["to"] == "accounts@baraka.co.ke" and draft["subject"].startswith("Tax invoice INV-")
    with django_capture_on_commit_callbacks(execute=True):
        sent = api.post(url(ws, "document-emails/"), {**doc, "to": draft["to"], "cc": "boss@baraka.co.ke", "subject": draft["subject"],
                                                       "message": draft["message"]}, format="json")
    assert sent.status_code == 201, sent.data
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert mail.to == ["accounts@baraka.co.ke"] and mail.cc == ["boss@baraka.co.ke"]
    assert "View and pay online: " in mail.body and "/p/" in mail.body
    assert "M-Pesa paybill: 247247" in mail.body and f"Account: {sent.data['document_number']}" in mail.body
    history = api.get(url(ws, "document-emails/"), doc).data
    assert history[0]["status"] == "sent" and history[0]["to"] == "accounts@baraka.co.ke"
    assert api.post(url(ws, "document-emails/"), {**doc, "to": "not-an-email", "subject": "x"}, format="json").status_code == 409


def test_email_a_payment_receipt(api, ws, day, mailoutbox, django_capture_on_commit_callbacks):
    cust = customer(api, ws, email="accounts@baraka.co.ke")
    inv = draft_invoice(api, ws, cust, day).data
    api.post(url(ws, f"invoices/{inv['id']}/issue/"))
    cash = next(a for a in api.get(url(ws, "ledger-accounts/")).data if a["code"] == "1000")
    pay = api.post(url(ws, "payments/"), {"customer_id": cust["id"], "payment_date": day, "amount": "1500", "method": "cash",
                                          "deposit_account_id": cash["id"], "allocations": [{"invoice_id": inv["id"], "amount": "1160"}]}, format="json").data
    doc = {"document_type": "payment", "object_id": pay["id"]}
    draft = api.get(url(ws, "document-emails/draft/"), doc).data
    assert draft["subject"].startswith("Payment receipt") and "received your payment" in draft["message"]
    with django_capture_on_commit_callbacks(execute=True):
        sent = api.post(url(ws, "document-emails/"), {**doc, "to": draft["to"], "subject": draft["subject"], "message": draft["message"]}, format="json")
    assert sent.status_code == 201, sent.data
    body = mailoutbox[0].body
    assert f"Invoice {inv['number'] if inv.get('number') else ''}" in body or "Invoice INV-" in body
    assert "Kept as credit on your account" in body and "Total KES 1,500.00" in body
