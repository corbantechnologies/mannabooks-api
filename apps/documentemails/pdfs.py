"""
Documents as PDF: the API renders HTML from one template and Chromium prints it to A4.

PDF_ENGINE picks the printer:
- "playwright" (default): Chromium on this machine, installed at build time (`playwright install --with-deps chromium`);
- "service": the separate PDF service (pdf-service/), at PDF_SERVICE_URL with PDF_SERVICE_KEY;
- "off": no PDFs; people print from the browser and emails go without an attachment.
"""
import base64
import functools
import logging
import os

import requests
from django.conf import settings
from django.template.loader import render_to_string

from apps.core.exceptions import BusinessRuleError

from .registry import DOCS

logger = logging.getLogger("mannabooks.pdf")
SECOND_DATE = {"invoice": ("due_date", "Due"), "quotation": ("valid_until", "Valid until"), "purchase_order": ("expected_date", "Needed by"),
               "service_order": ("expected_date", "Needed by")}
PARTY_LABEL = {"purchase_order": "Supplier", "service_order": "Supplier", "supplier_payment": "Paid to", "payment": "Received from",
               "delivery_note": "Deliver to"}


MARGINS = {"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"}
CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]


def enabled() -> bool:
    if settings.PDF_ENGINE == "service":
        return bool(settings.PDF_SERVICE_URL and settings.PDF_SERVICE_KEY)
    return settings.PDF_ENGINE == "playwright" and _chromium_installed()


@functools.cache
def _chromium_installed() -> bool:
    """Checked once per process: is Playwright's Chromium on this machine?"""
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            p.chromium.launch(args=CHROMIUM_ARGS).close()  # the headless shell has no executable_path of its own: try it
            return True
    except Exception as exc:  # noqa: BLE001 - no Playwright, or no browser: PDFs are simply off
        logger.warning("Chromium can't start, so PDF downloads are off (browsers path %s): %s",
                       os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "default"), exc)
        return False


def _print_here(html: str) -> bytes:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(args=CHROMIUM_ARGS)
        try:
            context = browser.new_context(java_script_enabled=False, offline=True)  # everything is inlined: no network
            page = context.new_page()
            page.set_content(html, wait_until="load", timeout=20000)
            return page.pdf(format="A4", print_background=True, margin=MARGINS)
        finally:
            browser.close()


def _print_by_service(html: str) -> bytes:
    try:
        res = requests.post(f"{settings.PDF_SERVICE_URL.rstrip('/')}/render", json={"html": html},
                            headers={"X-Render-Key": settings.PDF_SERVICE_KEY}, timeout=45)
    except requests.RequestException as exc:
        raise BusinessRuleError("The PDF service couldn't be reached. Try again, or use Print.") from exc
    if res.status_code != 200:
        logger.error("PDF service answered %s", res.status_code)
    return res.content if res.status_code == 200 else b""


def _money(value) -> str:
    return f"{value:,.2f}" if value is not None else ""


def _qty(value) -> str:
    return f"{value.normalize():f}" if value is not None else ""


def _image(url: str) -> str:
    """The logo or QR code as a data URI: the PDF service renders offline."""
    if not url:
        return ""
    try:
        res = requests.get(url, timeout=5)
        if res.ok and len(res.content) < 600_000 and res.headers.get("content-type", "").startswith("image/"):
            return f"data:{res.headers['content-type']};base64,{base64.b64encode(res.content).decode()}"
    except requests.RequestException:
        pass
    return ""


def _lines(doc_type, document, spec):
    if hasattr(document, "lines") and doc_type not in ("delivery_note",):
        out = []
        for line in document.lines.select_related("tax_rate"):
            price = getattr(line, "unit_price", None)
            if price is None:
                price = getattr(line, "unit_cost", None)
            unit = line.unit if getattr(line, "unit", "") and getattr(line, "unit_factor", 1) != 1 else ""
            out.append({"description": line.description, "quantity": f"{_qty(line.quantity)} {unit}".strip(), "price": _money(price),
                        "tax": _money(getattr(line, "tax_amount", None)), "amount": _money(getattr(line, "total_amount", None))})
        return out, True
    return [{"description": d, "quantity": q, "price": "", "tax": "", "amount": _money(a)} for d, q, a in spec.rows(document)], False


def html_for(workspace, doc_type: str, document) -> str:
    from apps.paymentoptions.models import PaymentOption

    spec = DOCS[doc_type]
    party = spec.party(document)
    second_field, second_label = SECOND_DATE.get(doc_type, ("", ""))
    lines, priced = _lines(doc_type, document, spec)
    total = spec.total(document)
    pay = []
    if doc_type in ("invoice", "quotation"):
        pay = [[x.replace("the document number", document.number) for x in o.lines()] for o in PaymentOption.objects.filter(workspace=workspace, show_on_documents=True)]
    context = {
        "title": spec.title(document), "number": document.number, "date": spec.date(document), "reference": getattr(document, "reference", ""),
        "second_date": getattr(document, second_field, None) if second_field else None, "second_label": second_label,
        "business": {"name": workspace.legal_name or workspace.name, "address": workspace.address, "phone": workspace.phone, "email": workspace.email,
                     "kra_pin": workspace.kra_pin, "vat_number": workspace.vat_number if workspace.vat_registered else ""},
        "logo": _image(workspace.logo_url),
        "party": party and {"name": party.name, "address": getattr(party, "address", ""), "kra_pin": getattr(party, "kra_pin", ""),
                            "phone": getattr(party, "phone", ""), "email": getattr(party, "email", "")},
        "party_label": PARTY_LABEL.get(doc_type, "Bill to"),
        "lines": lines, "priced": priced, "money": total is not None,
        "subtotal": _money(getattr(document, "subtotal", None)) if priced else "", "tax_total": _money(getattr(document, "tax_total", None)) if priced else "",
        "total": _money(total), "currency": getattr(document, "currency", "") or workspace.currency,
        "amount_paid": _money(document.amount_paid) if doc_type == "invoice" and document.amount_paid else "",
        "balance_due": _money(document.balance_due) if doc_type == "invoice" and document.status not in ("paid",) else "",
        "pay": pay, "notes": getattr(document, "notes", ""), "void": getattr(document, "status", "") == "void",
        "etims_number": getattr(document, "etims_cu_invoice_number", ""), "etims_signature": getattr(document, "etims_signature", ""),
        "etims_qr": _image(getattr(document, "etims_qr_url", "")),
    }
    return render_to_string("pdf/document.html", context)


def render(workspace, doc_type: str, document) -> bytes:
    if not enabled():
        raise BusinessRuleError("PDF downloads aren't set up yet. Use Print and choose Save as PDF.")
    html = html_for(workspace, doc_type, document)
    if settings.PDF_ENGINE == "service":
        pdf = _print_by_service(html)
    else:
        try:
            pdf = _print_here(html)
        except Exception:  # noqa: BLE001 - a browser crash or timeout must not become a 500
            logger.exception("Chromium couldn't print %s %s", doc_type, document.pk)
            pdf = b""
    if not pdf.startswith(b"%PDF"):
        raise BusinessRuleError("The PDF couldn't be made. Try again, or use Print.")
    return pdf


def filename(doc_type: str, document) -> str:
    return f"{DOCS[doc_type].title(document)} {document.number}.pdf".replace("/", "-")
