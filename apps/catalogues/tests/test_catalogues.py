from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from rest_framework.test import APIClient

from apps.invoices.tests.test_sales_flow import api, url, vat16, ws  # noqa: F401

pytestmark = pytest.mark.django_db
public = APIClient()


@pytest.fixture
def tech(api, ws):  # noqa: F811
    """Laptops (with a Gaming sub-category) and a phone."""
    laptops = api.post(url(ws, "product-categories/"), {"name": "Laptops"}, format="json").data
    gaming = api.post(url(ws, "product-categories/"), {"name": "Gaming laptops", "parent_id": laptops["id"]}, format="json").data
    phones = api.post(url(ws, "product-categories/"), {"name": "Phones"}, format="json").data

    def product(name, price, category):
        res = api.post(url(ws, "products/"), {"name": name, "sale_price": price, "tax_rate_id": vat16(ws), "category_id": category["id"]}, format="json")
        assert res.status_code == 201, res.data
        return res.data

    return {"book": product("ThinkPad X1", "100000", laptops), "old": product("Old netbook", "20000", laptops),
            "rog": product("ROG Strix", "200000", gaming), "phone": product("Pixel 9", "80000", phones), "laptops": laptops}


def make(api, ws, **body):  # noqa: F811
    res = api.post(url(ws, "catalogues/"), {"name": "Laptops", **body}, format="json")
    assert res.status_code == 201, res.data
    return res.data


def test_category_catalogue_writes_and_sends_the_quote(api, ws, tech, mailoutbox, django_capture_on_commit_callbacks):  # noqa: F811
    assert api.post(url(ws, "catalogues/"), {"name": "Empty"}, format="json").status_code == 400
    ws.email = "sales@example.com"
    ws.save(update_fields=["email"])
    cat = make(api, ws, category_ids=[tech["laptops"]["id"]], excluded_product_ids=[tech["old"]["id"]], intro="Our laptops")
    assert cat["product_count"] == 2 and cat["url"].endswith(f"/c/{cat['url'].rsplit('/', 1)[1]}")
    token = cat["url"].rsplit("/", 1)[1]

    page = public.get(f"/api/v1/shared/catalogues/{token}/").data
    assert [i["name"] for i in page["items"]] == ["ROG Strix", "ThinkPad X1"]  # the sub-category too, the excluded one left out
    assert page["items"][1]["price"] == "100000.00" and D(page["items"][1]["vat_percent"]) == 16 and page["items"][1]["in_stock"] is None

    pick = {"name": "Wanjiku Mwangi", "company": "Acme Ltd", "phone": "0722 000 111", "email": "wanjiku@acme.example",
            "notes": "Delivery to Westlands", "lines": [{"product_id": tech["book"]["id"], "quantity": "3"}]}
    phone = public.post(f"/api/v1/shared/catalogues/{token}/quote/", {**pick, "lines": [{"product_id": tech["phone"]["id"], "quantity": "1"}]}, format="json")
    assert phone.status_code == 409  # not in this catalogue
    with django_capture_on_commit_callbacks(execute=True):
        res = public.post(f"/api/v1/shared/catalogues/{token}/quote/", pick, format="json")
    assert res.status_code == 201, res.data
    assert res.data["status"] == "sent"
    assert any(m.to == ["wanjiku@acme.example"] for m in mailoutbox)  # the client's link
    assert any("sales@example.com" in m.to and m.subject.startswith("New quote request") for m in mailoutbox)  # the team

    quote = public.get(f"/api/v1/shared/quotes/{res.data['token']}/").data
    assert quote["ready"] and quote["total"] == "348000.00" and quote["lines"][0]["quantity"] == "3.000"

    from apps.leads.models import Lead
    from apps.quotations.models import Quotation

    q = Quotation.objects.get(public_token=res.data["token"])
    assert q.customer.name == "Acme Ltd" and q.catalogue_id is not None and "Westlands" in q.notes
    lead = Lead.objects.get(customer=q.customer)
    assert lead.name == "Wanjiku Mwangi" and lead.estimated_value == q.total

    again = public.post(f"/api/v1/shared/catalogues/{token}/quote/", {**pick, "company": "", "email": "", "phone": "+254722000111"}, format="json")
    assert Quotation.objects.get(public_token=again.data["token"]).customer_id == q.customer_id  # matched by phone
    assert Lead.objects.filter(customer=q.customer).count() == 1

    assert public.post(f"/api/v1/shared/quotes/{res.data['token']}/answer/", {"action": "accept"}, format="json").data["status"] == "accepted"
    assert public.post(f"/api/v1/shared/quotes/{res.data['token']}/answer/", {"action": "decline"}, format="json").status_code == 409
    staff = api.get(url(ws, f"quotations/{q.id}/")).data
    assert staff["status"] == "accepted" and staff["catalogue_name"] == "Laptops" and staff["public_url"].endswith(res.data["token"])
    assert api.get(url(ws, "catalogues/")).data["results"][0]["quote_count"] == 2


def test_customer_catalogue_reviewed_first(api, ws, tech, mailoutbox, django_capture_on_commit_callbacks):  # noqa: F811
    cust = api.post(url(ws, "customers/"), {"name": "Baraka Supplies Ltd", "email": "buy@baraka.example"}, format="json").data
    cat = make(api, ws, product_ids=[tech["rog"]["id"], tech["phone"]["id"]], customer_id=cust["id"], quote_mode="review", show_stock=True)
    token = cat["url"].rsplit("/", 1)[1]
    page = public.get(f"/api/v1/shared/catalogues/{token}/").data
    assert page["customer_name"] == "Baraka Supplies Ltd" and page["reviews_first"] and page["items"][0]["in_stock"] is True

    res = public.post(f"/api/v1/shared/catalogues/{token}/quote/", {"name": "Otieno", "phone": "0711000222",
                      "lines": [{"product_id": tech["phone"]["id"], "quantity": "10"}]}, format="json")
    assert res.status_code == 201 and res.data["status"] == "draft"
    draft = public.get(f"/api/v1/shared/quotes/{res.data['token']}/").data
    assert not draft["ready"] and draft["total"] is None and draft["lines"][0]["unit_price"] is None
    assert public.post(f"/api/v1/shared/quotes/{res.data['token']}/answer/", {"action": "accept"}, format="json").status_code == 409

    from apps.customers.models import Customer
    from apps.quotations.models import Quotation

    assert Customer.objects.filter(workspace=ws).count() == 1  # the catalogue's customer, no new one
    q = Quotation.objects.get(public_token=res.data["token"])
    with django_capture_on_commit_callbacks(execute=True):
        assert api.post(url(ws, f"quotations/{q.id}/status/"), {"action": "send"}, format="json").data["status"] == "sent"
    assert any(m.to == ["buy@baraka.example"] and res.data["token"] in m.body for m in mailoutbox)
    assert public.post(f"/api/v1/shared/quotes/{res.data['token']}/answer/", {"action": "decline"}, format="json").data["status"] == "declined"


def test_closed_catalogue_and_share_link(api, ws, tech):  # noqa: F811
    cat = make(api, ws, product_ids=[tech["book"]["id"]], show_prices=False, expires_on=(date.today() - timedelta(days=1)).isoformat())
    token = cat["url"].rsplit("/", 1)[1]
    assert public.get(f"/api/v1/shared/catalogues/{token}/").status_code == 409
    api.patch(url(ws, f"catalogues/{cat['id']}/"), {"expires_on": None}, format="json")
    page = public.get(f"/api/v1/shared/catalogues/{token}/").data
    assert page["items"][0]["price"] is None and page["reviews_first"]  # prices on request: always reviewed
    api.patch(url(ws, f"catalogues/{cat['id']}/"), {"is_active": False}, format="json")
    assert public.get(f"/api/v1/shared/catalogues/{token}/").status_code == 409

    cust = api.post(url(ws, "customers/"), {"name": "Walk-in Co"}, format="json").data
    quote = api.post(url(ws, "quotations/"), {"customer_id": cust["id"], "lines": [{"product_id": tech["book"]["id"], "quantity": "1"}]}, format="json").data
    link = api.post(url(ws, f"quotations/{quote['id']}/share/")).data["url"]
    assert link == api.post(url(ws, f"quotations/{quote['id']}/share/")).data["url"]
    shared = public.get(f"/api/v1/shared/quotes/{link.rsplit('/', 1)[1]}/").data
    assert shared["ready"] is False  # still a draft until it is sent


def test_analytics(api, ws, tech):  # noqa: F811
    cat = make(api, ws, category_ids=[tech["laptops"]["id"]])
    token = cat["url"].rsplit("/", 1)[1]
    public.get(f"/api/v1/shared/catalogues/{token}/")
    public.get(f"/api/v1/shared/catalogues/{token}/")
    pick = {"name": "Achieng", "phone": "0733000444", "lines": [{"product_id": tech["book"]["id"], "quantity": "2"}]}
    first = public.post(f"/api/v1/shared/catalogues/{token}/quote/", pick, format="json").data
    public.post(f"/api/v1/shared/catalogues/{token}/quote/", pick, format="json")
    public.post(f"/api/v1/shared/quotes/{first['token']}/answer/", {"action": "accept"}, format="json")
    data = api.get(url(ws, "catalogues/analytics/")).data
    assert data["totals"]["views"] == 2 and data["totals"]["requests"] == 2 and data["totals"]["accepted"] == 1
    assert data["totals"]["win_rate"] == 50.0 and data["totals"]["accepted_value"] == "232000.00"
    assert data["catalogues"][0]["request_rate"] == 100.0
    assert data["top_products"][0]["name"] == "ThinkPad X1" and data["top_products"][0]["times"] == 2


def test_email_the_link(api, ws, tech, mailoutbox, django_capture_on_commit_callbacks):  # noqa: F811
    cat = make(api, ws, product_ids=[tech["book"]["id"]])
    with django_capture_on_commit_callbacks(execute=True):
        res = api.post(url(ws, f"catalogues/{cat['id']}/send/"), {"to": ["buyer@acme.example"], "message": "Hello, our laptops."}, format="json")
    assert res.status_code == 202, res.data
    assert mailoutbox[-1].to == ["buyer@acme.example"] and cat["url"] in mailoutbox[-1].body


def test_client_describes_what_they_cant_find(api, ws, tech):  # noqa: F811
    cat = make(api, ws, category_ids=[tech["laptops"]["id"]])  # sends quotes at once, but not ones with unpriced items
    token = cat["url"].rsplit("/", 1)[1]
    base = {"name": "Kamau", "phone": "0700111222"}
    assert public.post(f"/api/v1/shared/catalogues/{token}/quote/", base, format="json").status_code == 409  # nothing asked for
    res = public.post(f"/api/v1/shared/catalogues/{token}/quote/", {**base, "lines": [{"product_id": tech["book"]["id"], "quantity": "1"}],
                      "wishes": [{"description": "Laptop bag, 15 inch", "quantity": "2"}, {"description": "  "}]}, format="json")
    assert res.status_code == 201 and res.data["status"] == "draft", res.data
    from apps.quotations.models import Quotation

    q = Quotation.objects.get(public_token=res.data["token"])
    lines = list(q.lines.order_by("line_no"))
    assert len(lines) == 2 and lines[1].product_id is None and lines[1].unit_price == 0 and lines[1].quantity == 2
    assert "Laptop bag" in lines[1].description and "aren't in the catalogue" in q.notes
    only = public.post(f"/api/v1/shared/catalogues/{token}/quote/", {**base, "wishes": [{"description": "Docking station"}]}, format="json")
    assert only.status_code == 201 and only.data["status"] == "draft"


def test_catalogue_pdf_carries_the_link(api, ws, tech, settings, monkeypatch):  # noqa: F811
    from apps.documentemails import pdfs

    cat = make(api, ws, category_ids=[tech["laptops"]["id"]])
    token = cat["url"].rsplit("/", 1)[1]
    assert api.get(url(ws, f"catalogues/{cat['id']}/pdf/")).status_code == 409  # PDFs off in tests
    printed = {}
    settings.PDF_ENGINE = "playwright"
    monkeypatch.setattr(pdfs, "_chromium_installed", lambda: True)
    monkeypatch.setattr(pdfs, "_print_here", lambda html: printed.setdefault("html", html) and b"%PDF-1.7 fake")
    res = api.get(url(ws, f"catalogues/{cat['id']}/pdf/"))
    assert res.status_code == 200 and res["Content-Type"] == "application/pdf" and "Laptops.pdf" in res["Content-Disposition"]
    html = printed["html"]
    assert cat["url"] in html and "data:image/svg+xml" in html and "ThinkPad X1" in html and "Pixel 9" not in html
    assert "100,000.00" in html and "plus 16% VAT" in html
    assert public.get(f"/api/v1/shared/catalogues/{token}/pdf/").status_code == 200
