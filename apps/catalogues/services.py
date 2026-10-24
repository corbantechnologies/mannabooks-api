"""
Shared catalogues: which products a catalogue shows, at what price, and turning a client's picks into a quotation
(matched to a customer, or a new customer and a lead in the CRM). The client then accepts or declines it on its link.
"""
import secrets
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.core.exceptions import BusinessRuleError
from apps.core.money import ZERO, q2

from .models import Catalogue

MAX_LINES, MAX_QTY, MAX_WISHES = 200, Decimal("100000"), 10


def open_catalogue(token: str) -> Catalogue:
    c = Catalogue.objects.select_related("workspace", "customer", "price_list").filter(token=token).first()
    if c is None or not c.is_active or not c.workspace.is_active or (c.expires_on and c.expires_on < timezone.localdate()):
        raise BusinessRuleError("This catalogue is no longer available. Ask the business for a new link.")
    return c


def _with_children(categories) -> set:
    """The categories' ids and every sub-category under them."""
    from apps.productcategories.models import ProductCategory

    ids = {c.pk for c in categories}
    frontier = set(ids)
    while frontier:
        frontier = set(ProductCategory.objects.filter(parent__in=frontier).exclude(pk__in=ids).values_list("pk", flat=True))
        ids |= frontier
    return ids


def products_of(catalogue: Catalogue):
    from apps.products.models import Product

    picked = Q(pk__in=catalogue.products.values("pk"))
    categories = list(catalogue.categories.all())
    if categories:
        picked |= Q(category__in=_with_children(categories))
    return (Product.objects.filter(workspace=catalogue.workspace, is_active=True).filter(picked)
            .exclude(pk__in=catalogue.excluded_products.values("pk")).select_related("category", "tax_rate").order_by("name"))


def price_list_of(catalogue: Catalogue):
    return catalogue.price_list or getattr(catalogue.customer, "price_list", None)


def items(catalogue: Catalogue) -> list[dict]:
    """What the client sees: prices before VAT, the VAT rate, and stock as yes or no."""
    from apps.core.sales import default_vat
    from apps.onlineorders.services import _on_hand
    from apps.pricelists.services import prices_for

    products = list(products_of(catalogue))
    prices = prices_for(catalogue.workspace, price_list_of(catalogue)) if catalogue.show_prices else {}
    stock = _on_hand(products) if catalogue.show_stock else {}
    vat = default_vat(catalogue.workspace)
    rows = []
    for p in products:
        rate = p.tax_rate if p.tax_rate_id else vat
        rows.append({
            "id": str(p.pk), "name": p.name, "code": p.code, "description": p.description, "category": p.category.name if p.category_id else "",
            "unit": p.unit, "image_url": p.image_url,
            "price": str(q2(prices.get(str(p.pk), p.sale_price))) if catalogue.show_prices else None,
            "vat_percent": str(rate.rate) if rate is not None and rate.kind == "vat" else "0",
            "in_stock": ((not p.track_inventory) or stock.get(p.pk, ZERO) > 0) if catalogue.show_stock else None,
        })
    return rows


def business_of(workspace) -> dict:
    return {"name": workspace.legal_name or workspace.name, "phone": workspace.phone, "email": workspace.email,
            "address": workspace.address, "logo_url": workspace.logo_url, "currency": workspace.currency}


# ---------------------------------------------------------------- who is asking
def _phone_key(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if digits.startswith("0"):
        digits = "254" + digits[1:]
    return digits[-9:] if len(digits) >= 9 else digits


def match_customer(workspace, *, name: str, company: str, phone: str, email: str, user=None):
    """The existing customer with this email or phone; else a new customer and a lead for the team to follow up."""
    from apps.customers.models import Customer
    from apps.leads.models import Lead
    from apps.sequences.services import next_value

    candidates = Customer.objects.filter(workspace=workspace, is_active=True)
    if email:
        found = candidates.filter(email__iexact=email).first()
        if found is not None:
            return found, None
    key = _phone_key(phone)
    if len(key) == 9:
        for c in candidates.exclude(phone="").only("id", "phone"):
            if _phone_key(c.phone) == key:
                return Customer.objects.get(pk=c.pk), None
    customer = Customer.objects.create(
        workspace=workspace, created_by=user, number=next_value(workspace, "customer"), name=(company or name)[:200],
        kind=Customer.Kind.COMPANY if company else Customer.Kind.INDIVIDUAL, email=email, phone=phone[:30],
        notes=f"Added from a catalogue request by {name}." if company else "Added from a catalogue request.",
    )
    lead = Lead.objects.filter(workspace=workspace, customer__isnull=True).filter(
        Q(email__iexact=email) if email else Q(pk__in=[])).first()
    if lead is None:
        lead = Lead(workspace=workspace, created_by=user, number=next_value(workspace, "lead"), name=name[:150], company=company[:200],
                    phone=phone[:30], email=email, source=Lead.Source.WEBSITE)
    lead.customer = customer
    lead.save()
    return customer, lead


# ---------------------------------------------------------------- the client's request
@transaction.atomic
def request_quote(catalogue: Catalogue, *, name: str, company: str = "", phone: str, email: str = "", notes: str = "", rows: list[dict],
                  wishes: list[dict] | None = None):
    """
    A quotation written from the client's picks: sent at once, or a draft for the team to review. `wishes` are things the
    client described because they weren't in the catalogue; they come in unpriced, so the quotation always waits for review.
    """
    from apps.quotations import services as quotes
    from apps.quotations.models import Quotation

    wishes = [w for w in (wishes or []) if str(w.get("description") or "").strip()]
    if not rows and not wishes:
        raise BusinessRuleError("Pick at least one item, or describe what you need.")
    if len(wishes) > MAX_WISHES:
        raise BusinessRuleError(f"Describe up to {MAX_WISHES} things you can't find.")
    if len(rows) > MAX_LINES:
        raise BusinessRuleError(f"A request can have up to {MAX_LINES} items.")
    name, company, email = name.strip(), company.strip(), email.strip()
    if not name or not phone.strip():
        raise BusinessRuleError("Enter your name and phone number.")
    wanted: dict[str, Decimal] = {}
    for row in rows:
        pid = str(row.get("product_id"))
        wanted[pid] = wanted.get(pid, ZERO) + _quantity(row)
    offered = {str(p.pk): p for p in products_of(catalogue).filter(pk__in=[k for k in wanted if _is_uuid(k)])}
    if len(offered) != len(wanted):
        raise BusinessRuleError("Something you picked is no longer in this catalogue. Refresh the page and try again.")

    workspace = catalogue.workspace
    lead = None
    if catalogue.customer_id:
        customer = catalogue.customer
    else:
        customer, lead = match_customer(workspace, name=name, company=company, phone=phone.strip(), email=email, user=catalogue.created_by)
    price_list = price_list_of(catalogue)
    from apps.pricelists.services import price_for

    # the prices the client saw, even if the customer they matched has a price list of their own
    lines = [{"product": offered[pid], "quantity": qty, "unit_price": price_for(offered[pid], price_list)} for pid, qty in wanted.items()]
    lines += [{"description": f"{str(w['description']).strip()[:200]} (not in the catalogue: price it)", "quantity": _quantity(w), "unit_price": ZERO}
              for w in wishes]
    reviews_first = catalogue.reviews_first or bool(wishes)
    who = ", ".join(x for x in (name, company, phone.strip(), email) if x)
    note = f"Requested through the catalogue \"{catalogue.name}\" by {who}."
    if notes.strip():
        note += f"\n\nFrom the client: {notes.strip()[:2000]}"
    if wishes:
        note += f"\n\nThe client described {len(wishes)} item(s) that aren't in the catalogue. Price them (or remove them) before sending."
    quotation = quotes.save(workspace, header={"customer": customer, "notes": note}, rows=lines, user=catalogue.created_by)
    quotation.catalogue, quotation.public_token = catalogue, secrets.token_urlsafe(18)
    quotation.contact_email = email or customer.email
    quotation.save(update_fields=["catalogue", "public_token", "contact_email", "updated_at"])
    if lead is not None:
        lead.interest = f"Quotation {quotation.number} from {catalogue.name}"[:255]
        lead.estimated_value = quotation.total
        lead.save(update_fields=["interest", "estimated_value", "updated_at"])
    if not reviews_first:
        quotes.change_status(quotation, "send")  # emails the client their link
    _tell_team(quotation, f"New quote request: {quotation.number} from {who}",
               f"{who} picked {len(wanted)} item(s) from \"{catalogue.name}\""
               + (f" and described {len(wishes)} they couldn't find" if wishes else "") + ".\n\n"
               + ("The quotation was sent to them." if not reviews_first else "It is a draft: review it and send it.")
               + f"\n\nOpen it: {_staff_link(quotation)}")
    return Quotation.objects.get(pk=quotation.pk)


def _quantity(row: dict) -> Decimal:
    try:
        quantity = Decimal(str(row.get("quantity") or 0))
    except ArithmeticError as exc:
        raise BusinessRuleError("Enter quantities as numbers.") from exc
    if quantity <= 0 or quantity > MAX_QTY:
        raise BusinessRuleError("Each quantity must be more than zero and at most 100,000.")
    return quantity


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------- the quote's link
def open_quote(token: str):
    from apps.quotations.models import Quotation

    q = Quotation.objects.select_related("workspace", "customer", "catalogue").filter(public_token=token).first() if token else None
    if q is None or not q.workspace.is_active:
        raise BusinessRuleError("This quote link doesn't work. Ask the business for a new one.")
    return q


def public_url(quotation) -> str | None:
    return f"{settings.FRONTEND_URL}/q/{quotation.public_token}" if quotation.public_token else None


def quote_data(q) -> dict:
    ready = q.status != "draft"
    return {
        "business": business_of(q.workspace), "customer": {"name": q.customer.name},
        "number": q.number, "status": q.status, "ready": ready, "issue_date": q.issue_date, "valid_until": q.valid_until,
        "is_expired": q.status in ("draft", "sent") and q.valid_until < timezone.localdate(),
        "currency": q.currency, "prices_include_tax": q.prices_include_tax, "catalogue_token": q.catalogue.token if q.catalogue_id else None,
        "subtotal": str(q.subtotal) if ready else None, "tax_total": str(q.tax_total) if ready else None, "total": str(q.total) if ready else None,
        "lines": [{"description": ln.description, "quantity": str(ln.quantity), "unit": ln.unit or (ln.product.unit if ln.product_id else ""),
                   "unit_price": str(ln.unit_price) if ready else None, "tax_rate_name": ln.tax_rate.name if ln.tax_rate else None,
                   "total_amount": str(ln.total_amount) if ready else None}
                  for ln in q.lines.select_related("tax_rate", "product")],
    }


def answer(q, action: str):
    """The client accepts or declines the quote on its link."""
    from apps.quotations import services as quotes

    if q.status != "sent":
        raise BusinessRuleError({"draft": "The business is still preparing this quote.", "accepted": "You have already accepted this quote.",
                                 "declined": "You have declined this quote.", "converted": "This quote is already being invoiced."}.get(q.status, "This quote can't be changed."))
    if action == "accept" and q.valid_until < timezone.localdate():
        raise BusinessRuleError("This quote has expired. Ask the business for a new one.")
    quotes.change_status(q, action)
    done = {"accept": "accepted", "decline": "declined"}[action]
    _tell_team(q, f"Quotation {q.number} {done} by {q.customer.name}",
               f"{q.customer.name} {done} quotation {q.number} ({q.currency} {q.total:,.2f}) on its link."
               + ("\n\nConvert it to an invoice when you are ready." if action == "accept" else "")
               + f"\n\nOpen it: {_staff_link(q)}")
    return q


def quote_sent(q) -> None:
    """Called when a linked quote goes out: email the client their link."""
    if not q.public_token or not q.contact_email:
        return
    business = q.workspace.legal_name or q.workspace.name
    body = (f"Hello {q.customer.name},\n\nYour quotation {q.number} from {business} is ready: {q.currency} {q.total:,.2f}, "
            f"valid until {q.valid_until:%d %b %Y}.\n\nSee it, download it or accept it here: {public_url(q)}\n\n{business}")
    _mail(f"Quotation {q.number} from {business}", body, [q.contact_email])


def _staff_link(q) -> str:
    return f"{settings.FRONTEND_URL}/w/{q.workspace.slug}/sales/quotations/{q.pk}"


def _tell_team(q, subject: str, body: str) -> None:
    emails = {e for e in (q.workspace.email, getattr(q.catalogue.created_by if q.catalogue_id else None, "email", "")) if e}
    if emails:
        _mail(subject, body, sorted(emails))


def _mail(subject: str, body: str, to: list[str]) -> None:
    from .tasks import send_catalogue_email

    transaction.on_commit(lambda: send_catalogue_email.delay(subject, body, to))


# ---------------------------------------------------------------- how catalogues are doing
def analytics(workspace, start=None, end=None) -> dict:
    """Per catalogue: views (all time), quote requests, accepted and their value; and the products clients ask for most."""
    from django.db.models import Count, DecimalField, Sum, Value
    from django.db.models.functions import Coalesce

    from apps.quotations.models import Quotation, QuotationLine

    won = ("accepted", "converted")
    quotes = Quotation.objects.filter(workspace=workspace, catalogue__isnull=False)
    if start:
        quotes = quotes.filter(issue_date__gte=start)
    if end:
        quotes = quotes.filter(issue_date__lte=end)
    zero = Value(ZERO, output_field=DecimalField(max_digits=18, decimal_places=2))
    per = {r["catalogue"]: r for r in quotes.values("catalogue").annotate(
        requests=Count("id"), accepted=Count("id", filter=Q(status__in=won)),
        requested_value=Coalesce(Sum("total"), zero), accepted_value=Coalesce(Sum("total", filter=Q(status__in=won)), zero))}
    rows = []
    for c in Catalogue.objects.filter(workspace=workspace).select_related("customer"):
        r = per.get(c.pk, {})
        requests, accepted = r.get("requests", 0), r.get("accepted", 0)
        rows.append({"id": str(c.pk), "name": c.name, "customer_name": c.customer.name if c.customer_id else None, "is_active": c.is_active,
                     "views": c.view_count, "requests": requests, "accepted": accepted,
                     "requested_value": str(r.get("requested_value", ZERO)), "accepted_value": str(r.get("accepted_value", ZERO)),
                     "request_rate": round(100 * requests / c.view_count, 1) if c.view_count else 0,
                     "win_rate": round(100 * accepted / requests, 1) if requests else 0})
    rows.sort(key=lambda x: (-x["requests"], -x["views"], x["name"]))
    top = (QuotationLine.objects.filter(quotation__in=quotes, product__isnull=False).values("product", "product__name")
           .annotate(times=Count("quotation", distinct=True), quantity=Sum("quantity"), value=Coalesce(Sum("total_amount"), zero))
           .order_by("-times", "-value")[:10])
    total = lambda key: sum((r[key] for r in rows), 0)  # noqa: E731
    requests, accepted = total("requests"), total("accepted")
    return {
        "totals": {"catalogues": len(rows), "views": total("views"), "requests": requests, "accepted": accepted,
                   "requested_value": str(sum((Decimal(r["requested_value"]) for r in rows), ZERO)),
                   "accepted_value": str(sum((Decimal(r["accepted_value"]) for r in rows), ZERO)),
                   "win_rate": round(100 * accepted / requests, 1) if requests else 0},
        "catalogues": rows,
        "top_products": [{"product_id": str(t["product"]), "name": t["product__name"], "times": t["times"], "quantity": str(t["quantity"]),
                          "value": str(t["value"])} for t in top],
    }


def send_link(catalogue: Catalogue, *, to: list[str], message: str, user=None) -> None:
    """Email the catalogue's link to the client, from the business (replies go to the business)."""
    from .tasks import send_catalogue_link

    if not to:
        raise BusinessRuleError("Enter who to send it to.")
    if not catalogue.is_active or (catalogue.expires_on and catalogue.expires_on < timezone.localdate()):
        raise BusinessRuleError("This catalogue is closed. Open it again before sending it.")
    reply_to = [x for x in (catalogue.workspace.email, getattr(user, "email", "")) if x][:1]
    pk = str(catalogue.pk)
    transaction.on_commit(lambda: send_catalogue_link.delay(pk, to, message, reply_to))


# ---------------------------------------------------------------- the catalogue as a PDF
MAX_PDF_ITEMS = 300


def pdf(catalogue: Catalogue) -> bytes:
    """The catalogue to print or attach: products by category, and the link (with a QR code) to pick and get the quotation."""
    from concurrent.futures import ThreadPoolExecutor

    import segno
    from django.template.loader import render_to_string

    from apps.documentemails import pdfs

    def html() -> str:
        rows = items(catalogue)[:MAX_PDF_ITEMS]
        with ThreadPoolExecutor(max_workers=8) as pool:  # pictures are fetched once, in parallel
            pictures = list(pool.map(pdfs.image_data, [r["image_url"] for r in rows]))
        groups: dict[str, list] = {}
        for r, picture in zip(rows, pictures, strict=True):
            vat = Decimal(r["vat_percent"])
            groups.setdefault(r["category"], []).append({
                **r, "image": picture, "price_text": f"{Decimal(r['price']):,.2f}" if r["price"] is not None else "",
                "vat_text": f"{vat.normalize():f}" if vat else "",
            })
        ws = catalogue.workspace
        return render_to_string("pdf/catalogue.html", {
            "name": catalogue.name, "intro": catalogue.intro, "business": business_of(ws), "logo": pdfs.image_data(ws.logo_url),
            "customer_name": catalogue.customer.name if catalogue.customer_id else "", "today": timezone.localdate(),
            "expires_on": catalogue.expires_on, "url": catalogue.url, "qr": segno.make(catalogue.url, error="m").svg_data_uri(scale=4, border=1),
            "reviews_first": catalogue.reviews_first, "show_prices": catalogue.show_prices, "currency": ws.currency,
            "groups": [{"name": k, "items": v} for k, v in sorted(groups.items(), key=lambda kv: (kv[0] == "", kv[0]))],
        })

    return pdfs.print_html(html, f"catalogue {catalogue.pk}")


def pdf_filename(catalogue: Catalogue) -> str:
    return f"{catalogue.name}.pdf".replace("/", "-").replace('"', "")
