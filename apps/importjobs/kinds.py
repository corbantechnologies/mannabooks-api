"""
More things to bring in from a spreadsheet: staff, leads, the chart of accounts, fixed assets, prices, units, recipes,
stock counts, and invoices and bills still unpaid in the previous system.

Each importer takes the checked rows and the shared error list and returns (imported, skipped). The runner in
services.py wraps them in one transaction and undoes everything when a row has an error or the file is only checked.
Rows matching an existing record are skipped (or, for prices, units and counts, update it), so importing a file twice
is safe.
"""
from collections import OrderedDict
from datetime import date, datetime
from decimal import Decimal

from apps.core.exceptions import BusinessRuleError

from .models import ImportJob

K = ImportJob.Kind

TEMPLATES = {
    K.EMPLOYEES: (["first_name", "last_name", "other_names", "email", "phone", "national_id", "kra_pin", "job_title", "department", "branch", "hire_date",
                   "basic_salary", "pay_method", "bank_name", "bank_account_number", "mpesa_phone", "nssf_number", "shif_number", "annual_leave_days"],
                  ["Jane", "Wanjiku", "", "jane@example.co.ke", "0711000222", "23456789", "A001234567B", "Accountant", "Finance", "", "2025-01-06",
                   "65000", "bank", "KCB", "1234567890", "", "NS123456", "SH123456", "21"]),
    K.LEADS: (["name", "company", "phone", "email", "source", "interest", "estimated_value", "notes"],
              ["Peter Otieno", "Otieno Hardware", "0722111333", "peter@otieno.co.ke", "event", "Stock and till for 2 shops", "120000", "Met at the expo"]),
    K.ACCOUNTS: (["code", "name", "type", "subtype", "parent_code", "description"],
                 ["6150", "Internet and phone", "expense", "expense", "", "Safaricom and internet bills"]),
    K.FIXED_ASSETS: (["name", "category", "serial_number", "purchase_date", "in_service_date", "cost", "residual_value", "method", "useful_life_years",
                      "rate_percent", "depreciation_to_date", "depreciated_to", "location", "asset_account_code", "notes"],
                     ["Toyota Probox KDA 123A", "motor_vehicles", "NCP160-123456", "2023-03-15", "", "1450000", "200000", "reducing_balance", "", "25",
                      "540000", "2025-12-31", "", "", "Delivery van"]),
    K.PRODUCT_PRICES: (["code", "name", "sale_price", "price_list", "list_price"],
                       ["CEM-50", "Cement 50kg", "980", "Wholesale", "920"]),
    K.PRODUCT_UNITS: (["product_code", "product_name", "unit", "factor", "sale_price"],
                      ["SODA-500", "Soda 500ml", "crate", "24", "1150"]),
    K.RECIPES: (["product_code", "product_name", "recipe_name", "output_quantity", "component_code", "component_name", "quantity"],
                ["BURGER", "Chicken burger", "", "1", "BUN", "Burger bun", "1"]),
    K.STOCK_COUNTS: (["warehouse", "product_code", "product_name", "counted_quantity"],
                     ["Main store", "CEM-50", "Cement 50kg", "118"]),
    K.OPEN_INVOICES: (["customer", "invoice_number", "invoice_date", "due_date", "amount_due"],
                      ["Baraka Supplies Ltd", "INV-0457", "2026-09-28", "2026-10-28", "48500"]),
    K.OPEN_BILLS: (["supplier", "supplier_invoice_number", "bill_date", "due_date", "amount_due"],
                   ["Bamburi Cement Ltd", "BC-77812", "2026-10-02", "2026-11-01", "126000"]),
}

# The permission each kind needs (the same one its screen needs).
PERMS = {
    K.EMPLOYEES: "employees.manage", K.LEADS: "crm.manage", K.ACCOUNTS: "ledgeraccounts.manage", K.FIXED_ASSETS: "fixedassets.manage",
    K.PRODUCT_PRICES: "products.manage", K.PRODUCT_UNITS: "products.manage", K.RECIPES: "manufacturing.manage",
    K.STOCK_COUNTS: "inventory.manage", K.OPEN_INVOICES: "invoices.issue", K.OPEN_BILLS: "bills.post",
}


# ---------------------------------------------------------------- helpers
def _flat(detail) -> str:
    if isinstance(detail, dict):
        return "; ".join(f"{k}: {_flat(v)}" for k, v in detail.items())
    if isinstance(detail, list):
        return " ".join(_flat(v) for v in detail)
    return str(detail)


def _number(value, field, errors, n, *, required=False):
    if value in ("", None):
        if required:
            errors.append({"row": n, "message": f"{field}: required."})
        return None
    try:
        return Decimal(str(value).replace(",", "").replace("KES", "").replace("KSh", "").strip())
    except Exception:  # noqa: BLE001 - any unreadable number is reported on its row
        errors.append({"row": n, "message": f"{field}: '{value}' isn't a number."})
        return None


DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d")


def _date(value, field, errors, n, *, required=False) -> date | None:
    if not value:
        if required:
            errors.append({"row": n, "message": f"{field}: required (e.g. 2026-10-31)."})
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    errors.append({"row": n, "message": f"{field}: '{value}' isn't a date. Use 2026-10-31 or 31/10/2026."})
    return None


class Products:
    """Find products by code, else by name (either column), ignoring case."""

    def __init__(self, workspace):
        from apps.products.models import Product

        self.by_code, self.by_name = {}, {}
        for p in Product.objects.filter(workspace=workspace):
            if p.code:
                self.by_code[p.code.lower()] = p
            self.by_name[p.name.lower()] = p

    def find(self, code, name):
        return self.by_code.get((code or "").lower()) or self.by_name.get((name or "").lower())


def _ctx(request):
    return {"request": request, "workspace": request.workspace}


# ---------------------------------------------------------------- staff and leads
def employees(request, rows, errors):
    from apps.branches.models import Branch
    from apps.departments.models import Department
    from apps.employees.models import Employee
    from apps.employees.serializers import EmployeeSerializer
    from apps.sequences.services import next_value

    ws = request.workspace
    existing = Employee.objects.filter(workspace=ws)
    taken = {v.lower() for e in existing for v in (e.national_id, e.email, e.kra_pin) if v}
    names = {f"{e.first_name} {e.last_name}".lower() for e in existing}
    departments = {d.name.lower(): d for d in Department.objects.filter(workspace=ws)}
    branches = {b.name.lower(): b for b in Branch.objects.filter(workspace=ws)}
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        keys = [row.get(k, "").lower() for k in ("national_id", "email", "kra_pin") if row.get(k)]
        full = f"{row.get('first_name', '')} {row.get('last_name', '')}".lower()
        if any(k in taken for k in keys) or (not keys and full in names):
            skipped += 1
            continue
        data = {k: row[k] for k in ("first_name", "last_name", "other_names", "email", "phone", "national_id", "kra_pin", "job_title", "bank_name",
                                    "bank_account_number", "mpesa_phone", "nssf_number", "shif_number") if row.get(k)}
        hired = _date(row.get("hire_date"), "hire_date", errors, n)
        if hired:
            data["hire_date"] = hired
        salary = _number(row.get("basic_salary"), "basic_salary", errors, n)
        if salary is not None:
            data["basic_salary"] = str(salary)
            data["on_payroll"] = salary > 0
        leave = _number(row.get("annual_leave_days"), "annual_leave_days", errors, n)
        if leave is not None:
            data["annual_leave_days"] = str(leave)
        method = row.get("pay_method", "").lower().replace("-", "").replace(" ", "")
        if method:
            if method not in ("bank", "mpesa"):
                errors.append({"row": n, "message": "pay_method: use bank or mpesa."})
            data["pay_method"] = method
        dept = row.get("department", "")
        if dept:
            if dept.lower() not in departments:
                departments[dept.lower()] = Department.objects.create(workspace=ws, created_by=request.user, name=dept[:120])
            data["department_id"] = str(departments[dept.lower()].pk)
        branch = row.get("branch", "")
        if branch:
            if branch.lower() not in branches:
                errors.append({"row": n, "message": f"branch: no branch called '{branch}'. Add it in Organisation > Branches first."})
            else:
                data["branch_id"] = str(branches[branch.lower()].pk)
        s = EmployeeSerializer(data=data, context=_ctx(request))
        if not s.is_valid():
            errors.append({"row": n, "message": _flat(s.errors)})
            continue
        s.save(workspace=ws, created_by=request.user, staff_number=next_value(ws, "employee"))
        taken.update(keys)
        names.add(full)
        imported += 1
    return imported, skipped


SOURCES = {"walk_in": "walk_in", "walkin": "walk_in", "call": "call", "phone": "call", "referral": "referral", "website": "website", "web": "website",
           "social": "social", "facebook": "social", "instagram": "social", "tiktok": "social", "x": "social", "event": "event", "expo": "event",
           "exhibition": "event"}


def leads(request, rows, errors):
    from apps.leads.models import Lead
    from apps.leads.serializers import LeadSerializer
    from apps.sequences.services import next_value

    ws = request.workspace
    taken = {v.lower() for lead in Lead.objects.filter(workspace=ws) for v in (lead.phone, lead.email) if v}
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        keys = [row[k].lower() for k in ("phone", "email") if row.get(k)]
        if any(k in taken for k in keys):
            skipped += 1
            continue
        data = {k: row[k] for k in ("name", "company", "phone", "email", "interest", "notes") if row.get(k)}
        data["source"] = SOURCES.get(row.get("source", "").lower().replace(" ", "_").replace("-", "_"), "other")
        value = _number(row.get("estimated_value"), "estimated_value", errors, n)
        if value is not None:
            data["estimated_value"] = str(value)
        s = LeadSerializer(data=data, context=_ctx(request))
        if not s.is_valid():
            errors.append({"row": n, "message": _flat(s.errors)})
            continue
        s.save(workspace=ws, created_by=request.user, number=next_value(ws, "lead"))
        taken.update(keys)
        imported += 1
    return imported, skipped


# ---------------------------------------------------------------- accounting
DEFAULT_SUBTYPE = {"asset": "current_asset", "liability": "current_liability", "equity": "equity", "income": "income", "expense": "expense"}


def accounts(request, rows, errors):
    from apps.ledgeraccounts.models import LedgerAccount
    from apps.ledgeraccounts.serializers import LedgerAccountSerializer

    ws = request.workspace
    by_code = {a.code: a for a in LedgerAccount.objects.filter(workspace=ws)}
    skipped = imported = 0
    pending = []
    for n, row in enumerate(rows, start=2):
        code = row.get("code", "")
        if code in by_code:
            skipped += 1
            continue
        kind = row.get("type", "").lower()
        if kind not in DEFAULT_SUBTYPE:
            errors.append({"row": n, "message": f"type: use one of {', '.join(DEFAULT_SUBTYPE)}."})
            continue
        pending.append((n, row, kind))
    # Parents first: an account whose parent is further down the file waits for it (a few passes cover any depth).
    for _ in range(6):
        waiting = []
        for n, row, kind in pending:
            parent_code = row.get("parent_code", "")
            if parent_code and parent_code not in by_code:
                waiting.append((n, row, kind))
                continue
            data = {"code": row["code"], "name": row.get("name", ""), "account_type": kind, "description": row.get("description", ""),
                    "subtype": (row.get("subtype") or DEFAULT_SUBTYPE[kind]).lower().replace(" ", "_")}
            if parent_code:
                data["parent_id"] = str(by_code[parent_code].pk)
            s = LedgerAccountSerializer(data=data, context=_ctx(request))
            if not s.is_valid():
                errors.append({"row": n, "message": _flat(s.errors)})
                continue
            by_code[row["code"]] = s.save(workspace=ws, created_by=request.user)
            imported += 1
        if len(waiting) == len(pending):
            break
        pending = waiting
    for n, row, _kind in pending:
        if row.get("parent_code") not in by_code:
            errors.append({"row": n, "message": f"parent_code: no account {row.get('parent_code')} in the chart or in this file."})
    return imported, skipped


def fixed_assets(request, rows, errors):
    from apps.branches.models import Branch
    from apps.fixedassets import services as assets
    from apps.fixedassets.models import FixedAsset
    from apps.fixedassets.serializers import FixedAssetSerializer
    from apps.ledgeraccounts.models import LedgerAccount

    ws = request.workspace
    existing = FixedAsset.objects.filter(workspace=ws)
    serials = {a.serial_number.lower() for a in existing if a.serial_number}
    named = {(a.name.lower(), a.purchase_date) for a in existing}
    categories = {c.value: c.value for c in FixedAsset.Category} | {c.label.lower(): c.value for c in FixedAsset.Category}
    methods = {m.value: m.value for m in FixedAsset.Method} | {"straight": "straight_line", "reducing": "reducing_balance"}
    branches = {b.name.lower(): b for b in Branch.objects.filter(workspace=ws)}
    codes = {a.code: a for a in LedgerAccount.objects.filter(workspace=ws)}
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        bought = _date(row.get("purchase_date"), "purchase_date", errors, n, required=True)
        serial = row.get("serial_number", "")
        if (serial and serial.lower() in serials) or (row.get("name", "").lower(), bought) in named:
            skipped += 1
            continue
        category = categories.get(row.get("category", "").lower().replace(" ", "_")) or categories.get(row.get("category", "").lower()) or "other"
        data = {"name": row.get("name", ""), "category": category, "serial_number": serial, "notes": row.get("notes", ""),
                "acquisition": FixedAsset.Acquisition.EXISTING, "purchase_date": bought}
        in_service = _date(row.get("in_service_date"), "in_service_date", errors, n)
        if in_service:
            data["in_service_date"] = in_service
        for field in ("cost", "residual_value", "rate_percent"):
            value = _number(row.get(field), field, errors, n, required=field == "cost")
            if value is not None:
                data[field] = str(value)
        years = _number(row.get("useful_life_years"), "useful_life_years", errors, n)
        if years is not None:
            data["useful_life_months"] = int(years * 12)
        if row.get("method"):
            method = methods.get(row["method"].lower().replace(" ", "_"))
            if method is None:
                errors.append({"row": n, "message": "method: use straight_line, reducing_balance or none."})
            else:
                data["method"] = method
        charged = _number(row.get("depreciation_to_date"), "depreciation_to_date", errors, n)
        if charged:
            data["opening_accumulated"] = str(charged)
            data["depreciated_to"] = _date(row.get("depreciated_to"), "depreciated_to", errors, n, required=True)
        if row.get("location"):
            branch = branches.get(row["location"].lower())
            if branch is None:
                errors.append({"row": n, "message": f"location: no branch called '{row['location']}'."})
            else:
                data["location_id"] = str(branch.pk)
        if row.get("asset_account_code"):
            account = codes.get(row["asset_account_code"])
            if account is None:
                errors.append({"row": n, "message": f"asset_account_code: no account {row['asset_account_code']}."})
            else:
                data["asset_account_id"] = str(account.pk)
        if bought is None:
            continue
        s = FixedAssetSerializer(data=data, context=_ctx(request))
        if not s.is_valid():
            errors.append({"row": n, "message": _flat(s.errors)})
            continue
        try:
            assets.save(ws, data=dict(s.validated_data), user=request.user)
        except BusinessRuleError as exc:
            errors.append({"row": n, "message": str(exc)})
            continue
        if serial:
            serials.add(serial.lower())
        named.add((data["name"].lower(), bought))
        imported += 1
    return imported, skipped


# ---------------------------------------------------------------- products
def product_prices(request, rows, errors):
    from apps.pricelists.models import PriceList, PriceListItem

    ws = request.workspace
    products = Products(ws)
    lists = {pl.name.lower(): pl for pl in PriceList.objects.filter(workspace=ws)}
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        product = products.find(row.get("code"), row.get("name"))
        if product is None:
            errors.append({"row": n, "message": f"No product with code '{row.get('code', '')}' or name '{row.get('name', '')}'."})
            continue
        changed = False
        price = _number(row.get("sale_price"), "sale_price", errors, n)
        if price is not None:
            if price < 0:
                errors.append({"row": n, "message": "sale_price: can't be negative."})
            elif price != product.sale_price:
                product.sale_price = price
                product.save(update_fields=["sale_price", "updated_at"])
                changed = True
        list_name = row.get("price_list", "")
        list_price = _number(row.get("list_price"), "list_price", errors, n)
        if list_name and list_price is None:
            errors.append({"row": n, "message": "list_price: enter the price for this price list."})
        elif list_price is not None:
            if not list_name:
                errors.append({"row": n, "message": "price_list: name the price list this price is for."})
            elif list_price < 0:
                errors.append({"row": n, "message": "list_price: can't be negative."})
            else:
                if list_name.lower() not in lists:
                    lists[list_name.lower()] = PriceList.objects.create(workspace=ws, created_by=request.user, name=list_name[:120])
                item, created = PriceListItem.objects.get_or_create(price_list=lists[list_name.lower()], product=product, defaults={"price": list_price})
                if not created and item.price != list_price:
                    item.price = list_price
                    item.save(update_fields=["price", "updated_at"])
                    changed = True
                changed = changed or created
        imported, skipped = (imported + 1, skipped) if changed else (imported, skipped + 1)
    return imported, skipped


def product_units(request, rows, errors):
    from apps.products.models import ProductUnit

    products = Products(request.workspace)
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        product = products.find(row.get("product_code"), row.get("product_name"))
        unit = row.get("unit", "").strip()[:20]
        factor = _number(row.get("factor"), "factor", errors, n, required=True)
        price = _number(row.get("sale_price"), "sale_price", errors, n)
        if product is None:
            errors.append({"row": n, "message": f"No product with code '{row.get('product_code', '')}' or name '{row.get('product_name', '')}'."})
            continue
        if not unit:
            errors.append({"row": n, "message": "unit: required, e.g. ctn or crate."})
            continue
        if unit == product.unit:
            errors.append({"row": n, "message": f"{unit} is {product}'s own unit; add a different one."})
            continue
        if factor is None or factor <= 0 or (price is not None and price < 0):
            if factor is not None:
                errors.append({"row": n, "message": "factor must be more than zero and sale_price not negative."})
            continue
        existing = ProductUnit.objects.filter(product=product, unit=unit).first()
        if existing is not None and existing.factor == factor and existing.sale_price == price:
            skipped += 1
            continue
        ProductUnit.objects.update_or_create(product=product, unit=unit, defaults={"factor": factor, "sale_price": price})
        imported += 1
    return imported, skipped


def recipes(request, rows, errors):
    from apps.billsofmaterials.models import BillOfMaterials
    from apps.billsofmaterials.serializers import BillOfMaterialsSerializer

    ws = request.workspace
    products = Products(ws)
    groups: OrderedDict = OrderedDict()
    for n, row in enumerate(rows, start=2):
        product = products.find(row.get("product_code"), row.get("product_name"))
        component = products.find(row.get("component_code"), row.get("component_name"))
        quantity = _number(row.get("quantity"), "quantity", errors, n, required=True)
        if product is None:
            errors.append({"row": n, "message": f"No product with code '{row.get('product_code', '')}' or name '{row.get('product_name', '')}'."})
            continue
        if component is None:
            errors.append({"row": n, "message": f"No component with code '{row.get('component_code', '')}' or name '{row.get('component_name', '')}'."})
            continue
        key = (product.pk, row.get("recipe_name", "").strip().lower())
        group = groups.setdefault(key, {"first_row": n, "product": product, "name": row.get("recipe_name", "").strip(), "output": None, "lines": {}})
        output = _number(row.get("output_quantity"), "output_quantity", errors, n)
        if output is not None:
            group["output"] = output
        if quantity is not None:
            group["lines"][component.pk] = group["lines"].get(component.pk, Decimal(0)) + quantity
    imported = skipped = 0
    for group in groups.values():
        existing = BillOfMaterials.objects.filter(workspace=ws, product=group["product"])
        if (existing.filter(name__iexact=group["name"]).exists() if group["name"] else existing.exists()):
            skipped += 1
            continue
        data = {"product_id": str(group["product"].pk), "name": group["name"], "output_quantity": str(group["output"] or 1),
                "lines": [{"component_id": str(pk), "quantity": str(q)} for pk, q in group["lines"].items()]}
        s = BillOfMaterialsSerializer(data=data, context=_ctx(request))
        if not s.is_valid():
            errors.append({"row": group["first_row"], "message": f"{group['product']}: {_flat(s.errors)}"})
            continue
        s.save(workspace=ws, created_by=request.user)
        imported += 1
    return imported, skipped


def stock_counts(request, rows, errors):
    """Counts go into the warehouse's count in progress (one is started if there is none), to check and post as usual."""
    from apps.stocktakes import services as takes
    from apps.stocktakes.models import StockTake
    from apps.warehouses.models import Warehouse
    from apps.warehouses.services import default_warehouse

    ws = request.workspace
    products = Products(ws)
    warehouses = {w.name.lower(): w for w in Warehouse.objects.filter(workspace=ws)}
    counts: dict = {}
    for n, row in enumerate(rows, start=2):
        name = row.get("warehouse", "")
        warehouse = warehouses.get(name.lower()) if name else default_warehouse(ws)
        product = products.find(row.get("product_code"), row.get("product_name"))
        quantity = _number(row.get("counted_quantity"), "counted_quantity", errors, n, required=True)
        if warehouse is None:
            errors.append({"row": n, "message": f"warehouse: no warehouse called '{name}'."})
            continue
        if product is None:
            errors.append({"row": n, "message": f"No product with code '{row.get('product_code', '')}' or name '{row.get('product_name', '')}'."})
            continue
        if not product.track_inventory:
            errors.append({"row": n, "message": f"{product} doesn't track stock."})
            continue
        if quantity is None:
            continue
        if quantity < 0:
            errors.append({"row": n, "message": "counted_quantity can't be negative."})
            continue
        per_wh = counts.setdefault(warehouse, {})
        per_wh[product] = per_wh.get(product, Decimal(0)) + quantity  # a scanner export lists each scan: add them up
    imported = 0
    for warehouse, per_product in counts.items():
        take = StockTake.objects.filter(warehouse=warehouse, status=StockTake.Status.COUNTING).first()
        try:
            if take is None:
                from django.utils import timezone

                take = takes.start(ws, warehouse=warehouse, count_date=timezone.localdate(), user=request.user)
            takes.record_counts(take, [{"product": p, "counted_quantity": q} for p, q in per_product.items()])
        except BusinessRuleError as exc:
            errors.append({"row": 1, "message": f"{warehouse}: {exc}"})
            continue
        imported += len(per_product)
    return imported, 0


# ---------------------------------------------------------------- unpaid documents from the previous system
def open_invoices(request, rows, errors):
    from apps.customers.models import Customer
    from apps.invoices import services as invoices
    from apps.invoices.models import Invoice

    ws = request.workspace
    customers = {c.name.lower(): c for c in Customer.objects.filter(workspace=ws)}
    numbers = {(x or "").lower() for x in Invoice.objects.filter(workspace=ws).exclude(number="").values_list("number", flat=True)}
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        number = row.get("invoice_number", "").strip()[:30]
        if number and number.lower() in numbers:
            skipped += 1
            continue
        customer = customers.get(row.get("customer", "").lower())
        issued = _date(row.get("invoice_date"), "invoice_date", errors, n, required=True)
        due = _date(row.get("due_date"), "due_date", errors, n)
        amount = _number(row.get("amount_due"), "amount_due", errors, n, required=True)
        if not number:
            errors.append({"row": n, "message": "invoice_number: required (the number the customer knows it by)."})
        if customer is None:
            errors.append({"row": n, "message": f"customer: no customer called '{row.get('customer', '')}'. Import your customers first."})
        if amount is not None and amount <= 0:
            errors.append({"row": n, "message": "amount_due must be more than zero."})
        if not (number and customer and issued and amount and amount > 0):
            continue
        try:
            invoices.bring_in_open(ws, customer=customer, number=number, issue_date=issued, due_date=due or issued, amount=amount, user=request.user)
        except BusinessRuleError as exc:
            errors.append({"row": n, "message": str(exc)})
            continue
        numbers.add(number.lower())
        imported += 1
    return imported, skipped


def open_bills(request, rows, errors):
    from apps.bills import services as bills
    from apps.bills.models import Bill
    from apps.suppliers.models import Supplier

    ws = request.workspace
    suppliers = {s.name.lower(): s for s in Supplier.objects.filter(workspace=ws)}
    recorded = {(b.supplier_id, b.supplier_invoice_number.lower()) for b in Bill.objects.filter(workspace=ws).exclude(status__in=["draft", "void"])}
    imported = skipped = 0
    for n, row in enumerate(rows, start=2):
        supplier = suppliers.get(row.get("supplier", "").lower())
        number = row.get("supplier_invoice_number", "").strip()[:60]
        if supplier and (supplier.pk, number.lower()) in recorded:
            skipped += 1
            continue
        billed = _date(row.get("bill_date"), "bill_date", errors, n, required=True)
        due = _date(row.get("due_date"), "due_date", errors, n)
        amount = _number(row.get("amount_due"), "amount_due", errors, n, required=True)
        if supplier is None:
            errors.append({"row": n, "message": f"supplier: no supplier called '{row.get('supplier', '')}'. Import your suppliers first."})
        if not number:
            errors.append({"row": n, "message": "supplier_invoice_number: required."})
        if amount is not None and amount <= 0:
            errors.append({"row": n, "message": "amount_due must be more than zero."})
        if not (supplier and number and billed and amount and amount > 0):
            continue
        try:
            bills.bring_in_open(ws, supplier=supplier, supplier_invoice_number=number, bill_date=billed, due_date=due or billed, amount=amount,
                                user=request.user)
        except BusinessRuleError as exc:
            errors.append({"row": n, "message": str(exc)})
            continue
        recorded.add((supplier.pk, number.lower()))
        imported += 1
    return imported, skipped


IMPORTERS = {
    K.EMPLOYEES: employees, K.LEADS: leads, K.ACCOUNTS: accounts, K.FIXED_ASSETS: fixed_assets, K.PRODUCT_PRICES: product_prices,
    K.PRODUCT_UNITS: product_units, K.RECIPES: recipes, K.STOCK_COUNTS: stock_counts, K.OPEN_INVOICES: open_invoices, K.OPEN_BILLS: open_bills,
}
