from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.utils import timezone

from apps.invoices.tests.test_sales_flow import url

pytestmark = pytest.mark.django_db


@pytest.fixture
def owed(workspace, owner):
    """An invoice 5 days overdue and one due in 3 days; a bill overdue and one due next month."""
    from apps.bills.services import bring_in_open as open_bill
    from apps.customers.models import Customer
    from apps.invoices.services import bring_in_open as open_invoice
    from apps.suppliers.models import Supplier

    today = timezone.localdate()
    acme = Customer.objects.create(workspace=workspace, number="CUS-1", name="Acme Ltd")
    mills = Supplier.objects.create(workspace=workspace, number="SUP-1", name="Unga Mills")
    open_invoice(workspace, customer=acme, number="OLD-1", issue_date=today - timedelta(days=35), due_date=today - timedelta(days=5), amount=D("5000"))
    open_invoice(workspace, customer=acme, number="OLD-2", issue_date=today - timedelta(days=27), due_date=today + timedelta(days=3), amount=D("2000"))
    open_bill(workspace, supplier=mills, supplier_invoice_number="UM-9", bill_date=today - timedelta(days=40), due_date=today - timedelta(days=10), amount=D("3000"))
    open_bill(workspace, supplier=mills, supplier_invoice_number="UM-10", bill_date=today, due_date=today + timedelta(days=30), amount=D("1000"))


def test_business_at_a_glance(workspace, owner, client_for, owed):
    data = client_for(owner).get(url(workspace, "reports/glance/")).data
    r, p = data["receivables"], data["payables"]
    assert D(r["total"]) == 7000 and D(r["overdue"]) == 5000 and r["overdue_count"] == 1 and D(r["due_soon"]) == 2000
    assert [i["number"] for i in r["list"]] == ["OLD-1", "OLD-2"] and r["list"][0]["days"] == -5
    assert r["top_overdue"][0]["name"] == "Acme Ltd"
    assert D(p["total"]) == 4000 and D(p["overdue"]) == 3000 and p["due_soon_count"] == 0 and p["list"][0]["number"]
    assert data["quotes"]["open_count"] == 0 and data["sales"] is not None and data["cash"] is not None


def test_parts_follow_permissions(workspace, owner, add_member, client_for, owed):
    cashier = add_member(workspace, "till@example.com", "cashier")
    data = client_for(cashier).get(url(workspace, "reports/glance/")).data
    assert data["sales"] is not None  # cash sales
    assert data["quotes"] is None and data["receivables"] is None and data["payables"] is None and data["cash"] is None
