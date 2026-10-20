"""
Bringing lists in from a spreadsheet (CSV), and taking them out.

Imports check every row with the same rules as the screens (the same serializers), then import all of them or none.
Rows matching an existing record (customer or supplier name, product name or code) are skipped, so importing the
same file twice adds nothing. Exports are CSV files Excel and Google Sheets open.
"""
import csv
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.core.exceptions import BusinessRuleError

from .models import ImportJob

K = ImportJob.Kind
MAX_ROWS = 5000
YES = {"yes", "y", "true", "1", "x"}

# The columns of each template (first row of the CSV), with an example row.
TEMPLATES = {
    K.CUSTOMERS: (["name", "kind", "kra_pin", "email", "phone", "address", "city", "payment_terms_days", "credit_limit", "notes"],
                  ["Baraka Supplies Ltd", "company", "P000111222Q", "accounts@baraka.co.ke", "0722000111", "Kenyatta Ave", "Nairobi", "30", "0", ""]),
    K.SUPPLIERS: (["name", "kind", "kra_pin", "email", "phone", "address", "city", "payment_terms_days", "bank_details", "notes"],
                  ["Bamburi Cement Ltd", "company", "P000222333R", "sales@bamburi.co.ke", "0733000222", "Mombasa Rd", "Nairobi", "30", "KCB 1234567890", ""]),
    K.PRODUCTS: (["name", "code", "kind", "category", "unit", "sale_price", "cost_price", "vat", "track_stock", "quantity_on_hand", "reorder_level", "description"],
                 ["Cement 50kg", "CEM-50", "goods", "Building materials", "bag", "950", "780", "VAT16", "yes", "120", "20", ""]),
    K.OPENING_BALANCES: (["account_code", "account_name", "debit", "credit"],
                         ["1100", "Bank account", "250000", "0"]),
}
VAT_CODES = "VAT16, VAT8, ZERO, EXEMPT or NONVAT"


def template_csv(kind: str) -> str:
    head, example = TEMPLATES[kind]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(head)
    writer.writerow(example)
    return out.getvalue()


def read_rows(upload) -> list[dict]:
    raw = upload.read()
    if len(raw) > 5 * 1024 * 1024:
        raise BusinessRuleError("The file is larger than 5 MB. Split it into smaller files.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise BusinessRuleError("The file is empty.")
    rows = []
    for row in reader:
        clean = {(k or "").strip().lower().replace(" ", "_"): (v or "").strip() for k, v in row.items() if k}
        if any(clean.values()):
            rows.append(clean)
    if not rows:
        raise BusinessRuleError("The file has headings but no rows.")
    if len(rows) > MAX_ROWS:
        raise BusinessRuleError(f"The file has {len(rows)} rows; import up to {MAX_ROWS} at a time.")
    return rows


def _money(value, field, errors, n):
    if value in ("", None):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        errors.append({"row": n, "message": f"{field}: '{value}' isn't a number."})
        return None


def _flat(detail) -> str:
    if isinstance(detail, dict):
        return "; ".join(f"{k}: {_flat(v)}" for k, v in detail.items())
    if isinstance(detail, list):
        return " ".join(_flat(v) for v in detail)
    return str(detail)


def _party_rows(workspace, rows, kind):
    from apps.customers.models import Customer
    from apps.suppliers.models import Supplier

    model = Customer if kind == K.CUSTOMERS else Supplier
    existing = {n.lower() for n in model.objects.filter(workspace=workspace).values_list("name", flat=True)}
    keep, skipped, seen = [], 0, set()
    for n, row in enumerate(rows, start=2):
        name = row.get("name", "")
        if name.lower() in existing or name.lower() in seen:
            skipped += 1
            continue
        seen.add(name.lower())
        data = {k: v for k, v in row.items() if v != "" and k in TEMPLATES[kind][0]}
        data["kind"] = (data.get("kind") or "company").lower()
        keep.append((n, data))
    return keep, skipped


def _product_rows(workspace, rows):
    from apps.products.models import Product
    from apps.taxrates.models import TaxRate

    existing = {(n or "").lower() for n in Product.objects.filter(workspace=workspace).values_list("name", flat=True)}
    codes = {(c or "").lower() for c in Product.objects.filter(workspace=workspace).exclude(code="").values_list("code", flat=True)}
    rates = {r.code.upper(): r for r in TaxRate.objects.filter(workspace=workspace, kind="vat")}
    keep, skipped, errors, seen = [], 0, [], set()
    for n, row in enumerate(rows, start=2):
        name, code = row.get("name", ""), row.get("code", "")
        if name.lower() in existing or (code and code.lower() in codes) or name.lower() in seen:
            skipped += 1
            continue
        seen.add(name.lower())
        kind = (row.get("kind") or "goods").lower()
        track = (row.get("track_stock") or "").lower() in YES and kind == "goods"
        data = {"name": name, "code": code, "kind": kind, "unit": row.get("unit") or "pcs", "description": row.get("description", ""),
                "track_inventory": track}
        for field in ("sale_price", "cost_price", "reorder_level"):
            value = _money(row.get(field), field, errors, n)
            if value is not None:
                data[field] = str(value)
        vat = (row.get("vat") or "").upper()
        if vat:
            if vat not in rates:
                errors.append({"row": n, "message": f"vat: '{vat}' isn't a VAT code. Use {VAT_CODES}."})
            else:
                data["tax_rate_id"] = str(rates[vat].pk)
        quantity = _money(row.get("quantity_on_hand"), "quantity_on_hand", errors, n)
        if quantity:
            if not track:
                errors.append({"row": n, "message": "quantity_on_hand: set track_stock to yes to record stock."})
            data["opening_quantity"] = str(quantity)
        keep.append((n, {**data, "_category": row.get("category", "")}))
    return keep, skipped, errors


def _category_id(workspace, name: str, cache: dict, commit: bool):
    from apps.productcategories.models import ProductCategory

    if not name:
        return None
    key = name.lower()
    if key not in cache:
        found = ProductCategory.objects.filter(workspace=workspace, name__iexact=name).first()
        if found is None and commit:
            found = ProductCategory.objects.create(workspace=workspace, name=name[:120])
        cache[key] = str(found.pk) if found else None
    return cache[key]


def _opening_rows(workspace, rows, errors):
    from apps.ledgeraccounts.models import LedgerAccount

    accounts = {a.code: a for a in LedgerAccount.objects.filter(workspace=workspace)}
    lines, debit_total, credit_total = [], Decimal(0), Decimal(0)
    for n, row in enumerate(rows, start=2):
        code = row.get("account_code", "")
        account = accounts.get(code)
        if account is None:
            errors.append({"row": n, "message": f"account_code: no account {code or '(blank)'} in the chart of accounts."})
            continue
        debit = _money(row.get("debit"), "debit", errors, n) or Decimal(0)
        credit = _money(row.get("credit"), "credit", errors, n) or Decimal(0)
        if debit < 0 or credit < 0:
            errors.append({"row": n, "message": "Amounts can't be negative: put the amount in the other column."})
        if debit and credit:
            errors.append({"row": n, "message": f"{code}: enter a debit or a credit, not both."})
        lines.append({"account": account, "debit": debit, "credit": credit})
        debit_total, credit_total = debit_total + debit, credit_total + credit
    return lines, debit_total, credit_total


def run(request, kind: str, upload, *, commit: bool, as_of=None) -> ImportJob:
    """Check (and, with `commit`, import) a CSV. Returns the job with its errors; nothing is saved unless every row is right."""
    workspace, user = request.workspace, request.user
    rows = read_rows(upload)
    errors: list[dict] = []
    imported = skipped = 0
    try:
        with transaction.atomic():
            if kind in (K.CUSTOMERS, K.SUPPLIERS):
                imported, skipped = _import_parties(request, kind, rows, errors)
            elif kind == K.PRODUCTS:
                imported, skipped = _import_products(request, rows, errors, commit)
            else:
                imported = _import_opening(workspace, rows, errors, as_of, user)
            if errors or not commit:
                raise _Rollback()
    except _Rollback:
        pass
    status = ImportJob.Status.FAILED if errors else ImportJob.Status.IMPORTED if commit else ImportJob.Status.CHECKED
    return ImportJob.objects.create(workspace=workspace, created_by=user, kind=kind, filename=getattr(upload, "name", "upload.csv")[:255], status=status,
                                    total_rows=len(rows), imported_rows=imported if not errors else 0, skipped_rows=skipped, errors=errors[:200])


class _Rollback(Exception):
    pass


def _import_parties(request, kind, rows, errors):
    from apps.customers.serializers import CustomerSerializer
    from apps.sequences.services import next_value
    from apps.suppliers.serializers import SupplierSerializer

    serializer_class, key = (CustomerSerializer, "customer") if kind == K.CUSTOMERS else (SupplierSerializer, "supplier")
    keep, skipped = _party_rows(request.workspace, rows, kind)
    for n, data in keep:
        s = serializer_class(data=data, context={"request": request, "workspace": request.workspace})
        if not s.is_valid():
            errors.append({"row": n, "message": _flat(s.errors)})
            continue
        s.save(workspace=request.workspace, created_by=request.user, number=next_value(request.workspace, key))
    return len(keep), skipped


def _import_products(request, rows, errors, commit):
    from apps.products.serializers import ProductSerializer

    keep, skipped, row_errors = _product_rows(request.workspace, rows)
    errors.extend(row_errors)
    cache: dict = {}
    for n, data in keep:
        category = data.pop("_category")
        data["category_id"] = _category_id(request.workspace, category, cache, commit=True)  # rolled back if this is only a check
        s = ProductSerializer(data=data, context={"request": request, "workspace": request.workspace})
        if not s.is_valid():
            errors.append({"row": n, "message": _flat(s.errors)})
            continue
        try:
            with transaction.atomic():
                s.save(workspace=request.workspace, created_by=request.user)
        except BusinessRuleError as exc:
            errors.append({"row": n, "message": str(exc)})
    return len(keep), skipped


def _import_opening(workspace, rows, errors, as_of, user):
    from apps.openingbalances import services as opening
    from apps.openingbalances.models import OpeningBalance

    if as_of is None:
        raise BusinessRuleError("Choose the date the balances are at (the day before you start on MannaBooks).")
    lines, debit, credit = _opening_rows(workspace, rows, errors)
    ob = OpeningBalance.objects.filter(workspace=workspace).first()
    if ob is not None and ob.status == OpeningBalance.Status.POSTED:
        errors.append({"row": 1, "message": "The opening balances are already posted. Unpost them in Accounting > Opening balances first."})
        return 0
    if errors:
        return 0
    if ob is None:
        ob = OpeningBalance.objects.create(workspace=workspace, created_by=user, as_of_date=as_of)
    ob.as_of_date = as_of
    ob.save(update_fields=["as_of_date", "updated_at"])
    opening.save_lines(ob, lines)  # saved as a draft: check it and post it in Accounting > Opening balances
    return len(lines)


# ---------------------------------------------------------------- exports
EXPORTS = {
    "customers": "customers.view", "suppliers": "suppliers.view", "products": "products.view", "accounts": "ledgeraccounts.view",
    "invoices": "invoices.view", "bills": "bills.view", "journal": "journals.view",
}


def export_csv(workspace, kind: str, *, from_date=None, to_date=None) -> str:
    out = io.StringIO()
    w = csv.writer(out)
    if kind == "customers":
        from apps.customers.models import Customer

        w.writerow(["number", "name", "kind", "kra_pin", "email", "phone", "address", "city", "payment_terms_days", "credit_limit", "active"])
        for c in Customer.objects.filter(workspace=workspace).order_by("number"):
            w.writerow([c.number, c.name, c.kind, c.kra_pin, c.email, c.phone, c.address, c.city, c.payment_terms_days, c.credit_limit, c.is_active])
    elif kind == "suppliers":
        from apps.suppliers.models import Supplier

        w.writerow(["number", "name", "kind", "kra_pin", "email", "phone", "address", "city", "payment_terms_days", "bank_details", "active"])
        for s in Supplier.objects.filter(workspace=workspace).order_by("number"):
            w.writerow([s.number, s.name, s.kind, s.kra_pin, s.email, s.phone, s.address, s.city, s.payment_terms_days, s.bank_details, s.is_active])
    elif kind == "products":
        from django.db.models import Sum

        from apps.products.models import Product

        w.writerow(["code", "name", "kind", "category", "unit", "sale_price", "cost_price", "vat", "track_stock", "quantity_on_hand", "reorder_level", "active"])
        for p in Product.objects.filter(workspace=workspace).select_related("category", "tax_rate").annotate(on_hand=Sum("stock_levels__quantity")).order_by("name"):
            w.writerow([p.code, p.name, p.kind, p.category.name if p.category_id else "", p.unit, p.sale_price, p.cost_price, p.tax_rate.code if p.tax_rate_id else "",
                        "yes" if p.track_inventory else "no", p.on_hand if p.track_inventory else "", p.reorder_level, p.is_active])
    elif kind == "accounts":
        from apps.ledgeraccounts.models import LedgerAccount
        from apps.reports.services import account_balances

        balances = account_balances(workspace, to_date=to_date)
        w.writerow(["code", "name", "type", "subtype", "debit_total", "credit_total", "balance", "active"])
        for a in LedgerAccount.objects.filter(workspace=workspace).order_by("code"):
            d, c = balances.get(a.pk, (0, 0))
            w.writerow([a.code, a.name, a.account_type, a.subtype, d, c, d - c, a.is_active])
    elif kind == "invoices":
        from apps.invoices.models import Invoice

        qs = Invoice.objects.filter(workspace=workspace).select_related("customer").order_by("issue_date", "number")
        if from_date:
            qs = qs.filter(issue_date__gte=from_date)
        if to_date:
            qs = qs.filter(issue_date__lte=to_date)
        w.writerow(["number", "kind", "date", "due_date", "customer", "customer_kra_pin", "status", "currency", "subtotal", "vat", "total", "paid", "balance_due"])
        for i in qs:
            w.writerow([i.number, i.kind, i.issue_date, i.due_date, i.customer.name, i.customer.kra_pin, i.status, i.currency, i.subtotal, i.tax_total, i.total,
                        i.amount_paid, i.balance_due])
    elif kind == "bills":
        from apps.bills.models import Bill

        qs = Bill.objects.filter(workspace=workspace).select_related("supplier").order_by("bill_date")
        if from_date:
            qs = qs.filter(bill_date__gte=from_date)
        if to_date:
            qs = qs.filter(bill_date__lte=to_date)
        w.writerow(["number", "supplier_invoice", "date", "due_date", "supplier", "supplier_kra_pin", "status", "subtotal", "vat", "total", "balance_due"])
        for b in qs:
            w.writerow([b.number, b.supplier_invoice_number, b.bill_date, b.due_date, b.supplier.name, b.supplier.kra_pin, b.status, b.subtotal, b.tax_total,
                        b.total, b.balance_due])
    elif kind == "journal":
        from apps.journals.models import JournalLine

        qs = (JournalLine.objects.filter(entry__workspace=workspace).exclude(entry__status="draft").select_related("entry", "account")
              .order_by("entry__entry_date", "entry__number"))
        if from_date:
            qs = qs.filter(entry__entry_date__gte=from_date)
        if to_date:
            qs = qs.filter(entry__entry_date__lte=to_date)
        w.writerow(["date", "entry", "source", "reference", "account_code", "account", "description", "debit", "credit"])
        for line in qs.iterator():
            w.writerow([line.entry.entry_date, line.entry.number, line.entry.source, line.entry.reference, line.account.code, line.account.name,
                        line.description, line.debit, line.credit])
    else:
        raise BusinessRuleError("Unknown export.")
    return out.getvalue()
