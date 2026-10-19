from django.db import models

from apps.core.documents import PurchaseDocument, PurchaseLine
from apps.core.money import MONEY_FIELD


class Bill(PurchaseDocument):
    """
    A supplier's invoice: what the business owes. Posting it records the payable and input VAT, clears
    "Goods received not invoiced" for delivered goods, and stocks items bought without a delivery note.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Unpaid"
        PARTIALLY_PAID = "partially_paid", "Partly paid"
        PAID = "paid", "Paid"
        VOID = "void", "Void"

    supplier_invoice_number = models.CharField(max_length=60)
    supplier_etims_number = models.CharField(max_length=80, blank=True, help_text="The CU invoice number on the supplier's eTIMS invoice")
    bill_date = models.DateField()
    due_date = models.DateField()
    purchase_order = models.ForeignKey("purchaseorders.PurchaseOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="bills")
    goods_receipt = models.ForeignKey("goodsreceipts.GoodsReceipt", null=True, blank=True, on_delete=models.PROTECT, related_name="bills")
    service_order = models.ForeignKey("serviceorders.ServiceOrder", null=True, blank=True, on_delete=models.PROTECT, related_name="bills")
    warehouse = models.ForeignKey("warehouses.Warehouse", null=True, blank=True, on_delete=models.PROTECT, related_name="+",
                                  help_text="Where stock bought on this bill goes")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    amount_paid = models.DecimalField(**MONEY_FIELD, default=0)
    balance_due = models.DecimalField(**MONEY_FIELD, default=0)
    void_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-bill_date", "-created_at"]
        indexes = [models.Index(fields=["workspace", "status"]), models.Index(fields=["workspace", "supplier"])]


class BillLine(PurchaseLine):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="lines")
    goods_receipt_line = models.ForeignKey("goodsreceipts.GoodsReceiptLine", null=True, blank=True, on_delete=models.PROTECT, related_name="bill_lines")
    order_line = models.ForeignKey("purchaseorders.PurchaseOrderLine", null=True, blank=True, on_delete=models.PROTECT, related_name="bill_lines")
