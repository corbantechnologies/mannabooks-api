"""
Sending sales documents to KRA eTIMS for signing.

`request_signing` is called whenever an invoice, cash sale or credit note is issued:
- eTIMS switched off for the platform (ETIMS_ENABLED=False, until KRA approval): the document is
  marked "Signing switched off" and nothing is sent;
- no active device for the workspace: marked "Device not set up";
- otherwise a submission is queued and a Celery worker sends it, retrying on failure.
"""
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.money import q2

from .models import EtimsSubmission

DOC_CODES = {"invoice": ("N", "S"), "receipt": ("N", "S"), "credit_note": ("N", "R")}  # sales type, receipt type


def request_signing(document, document_type: str) -> None:
    from apps.etimsdevices.models import EtimsDevice

    if not settings.ETIMS_ENABLED:
        _mark(document, "disabled")
        return
    device = EtimsDevice.objects.select_for_update().filter(workspace=document.workspace, is_active=True).first()
    if device is None:
        _mark(document, "not_configured")
        return
    device.last_invoice_number += 1
    device.save(update_fields=["last_invoice_number", "updated_at"])
    submission = EtimsSubmission.objects.create(
        workspace=document.workspace, document_type=document_type, document_id=document.pk,
        document_number=document.number, kra_invoice_number=device.last_invoice_number,
        payload=build_payload(document, document_type, device.last_invoice_number),
    )
    _mark(document, "pending")
    from .tasks import send_submission

    transaction.on_commit(lambda: send_submission.delay(str(submission.pk)))


def _mark(document, status: str) -> None:
    document.etims_status = status
    document.save(update_fields=["etims_status", "updated_at"])


def build_payload(document, document_type: str, invoice_number: int) -> dict:
    """The OSCU saveSales body for a document (amounts VAT inclusive, as KRA expects)."""
    sales_type, receipt_type = DOC_CODES[document_type]
    lines, taxable, tax = [], {}, {}
    for n, line in enumerate(document.lines.select_related("tax_rate", "product"), start=1):
        code = (line.tax_rate.etims_code if line.tax_rate else "") or "D"
        gross = line.total_amount
        taxable[code] = taxable.get(code, Decimal(0)) + gross
        tax[code] = tax.get(code, Decimal(0)) + line.tax_amount
        lines.append({
            "itemSeq": n,
            "itemCd": (line.product.code if line.product and line.product.code else f"MB{n:05d}"),
            "itemClsCd": "",
            "itemNm": line.description[:200],
            "qty": float(line.quantity),
            "prc": float(q2(gross / line.quantity)) if line.quantity else 0.0,
            "splyAmt": float(gross),
            "dcRt": float(line.discount_percent),
            "dcAmt": float(line.discount_amount),
            "taxTyCd": code,
            "taxblAmt": float(gross),
            "taxAmt": float(line.tax_amount),
            "totAmt": float(gross),
        })
    customer = getattr(document, "customer", None)
    now = timezone.localtime()
    body = {
        "invcNo": invoice_number,
        "orgInvcNo": 0,
        "custTin": (customer.kra_pin if customer else getattr(document, "customer_pin", "")) or "",
        "custNm": (customer.name if customer else getattr(document, "customer_name", "")) or "",
        "salesTyCd": sales_type,
        "rcptTyCd": receipt_type,
        "pmtTyCd": "01",
        "salesSttsCd": "02",
        "cfmDt": now.strftime("%Y%m%d%H%M%S"),
        "salesDt": document.issue_date.strftime("%Y%m%d"),
        "totItemCnt": len(lines),
        "totTaxblAmt": float(sum(taxable.values(), Decimal(0))),
        "totTaxAmt": float(sum(tax.values(), Decimal(0))),
        "totAmt": float(document.total),
        "itemList": lines,
    }
    for code in "ABCDE":
        body[f"taxblAmt{code}"] = float(taxable.get(code, 0))
        body[f"taxAmt{code}"] = float(tax.get(code, 0))
    return body


def apply_result(submission: EtimsSubmission, data: dict) -> None:
    """Store KRA's signature on the submission and the document."""
    from apps.creditnotes.models import CreditNote
    from apps.invoices.models import Invoice
    from apps.receipts.models import Receipt

    model = {"invoice": Invoice, "receipt": Receipt, "credit_note": CreditNote}[submission.document_type]
    info = data.get("data") or {}
    document = model.objects.get(pk=submission.document_id)
    document.etims_status = "signed"
    document.etims_cu_invoice_number = f"{info.get('sdcId', '')}/{info.get('rcptNo', submission.kra_invoice_number)}"
    document.etims_signature = str(info.get("rcptSign", ""))[:200]
    document.etims_qr_url = str(info.get("qrUrl", ""))[:500]
    document.etims_signed_at = timezone.now()
    document.save(update_fields=["etims_status", "etims_cu_invoice_number", "etims_signature", "etims_qr_url", "etims_signed_at", "updated_at"])
    submission.status, submission.response, submission.signed_at = EtimsSubmission.Status.SIGNED, data, timezone.now()
    submission.save(update_fields=["status", "response", "signed_at", "updated_at"])
