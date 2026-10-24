from rest_framework import serializers


class TrialBalanceRowSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    account_type = serializers.CharField()
    debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2)


class TrialBalanceSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    rows = TrialBalanceRowSerializer(many=True)
    total_debit = serializers.DecimalField(max_digits=18, decimal_places=2)
    total_credit = serializers.DecimalField(max_digits=18, decimal_places=2)
    balanced = serializers.BooleanField()



M = {"max_digits": 18, "decimal_places": 2}


class ReportRowSerializer(serializers.Serializer):
    account_id = serializers.UUIDField(allow_null=True)
    code = serializers.CharField(allow_blank=True)
    name = serializers.CharField()
    amount = serializers.DecimalField(**M)
    compare = serializers.DecimalField(**M)


class ReportSectionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    rows = ReportRowSerializer(many=True)
    total = serializers.DecimalField(**M)
    compare_total = serializers.DecimalField(**M)


class SideBySideColumnSerializer(serializers.Serializer):
    id = serializers.UUIDField(allow_null=True, help_text="Null: lines not tagged with any")
    name = serializers.CharField()


class SideBySideRowSerializer(serializers.Serializer):
    account_id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    amounts = serializers.ListField(child=serializers.DecimalField(**M), help_text="One per column")
    total = serializers.DecimalField(**M)


class SideBySideSectionSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    rows = SideBySideRowSerializer(many=True)
    totals = serializers.ListField(child=serializers.DecimalField(**M))
    total = serializers.DecimalField(**M)


class ProfitAndLossByDimensionSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    dimension = serializers.CharField()
    dimension_label = serializers.CharField()
    columns = SideBySideColumnSerializer(many=True)
    sections = SideBySideSectionSerializer(many=True)
    gross_profit = serializers.ListField(child=serializers.DecimalField(**M), help_text="One per column, then the total")
    operating_profit = serializers.ListField(child=serializers.DecimalField(**M))
    net_profit = serializers.ListField(child=serializers.DecimalField(**M))


class ProfitAndLossSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    compare_from = serializers.DateField(allow_null=True)
    compare_to = serializers.DateField(allow_null=True)
    sections = ReportSectionSerializer(many=True)
    gross_profit = serializers.DecimalField(**M)
    operating_profit = serializers.DecimalField(**M)
    net_profit = serializers.DecimalField(**M)
    compare_gross_profit = serializers.DecimalField(**M)
    compare_operating_profit = serializers.DecimalField(**M)
    compare_net_profit = serializers.DecimalField(**M)


class BalanceSheetSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    compare_as_of = serializers.DateField(allow_null=True)
    groups = ReportSectionSerializer(many=True)
    total_assets = serializers.DecimalField(**M)
    total_liabilities = serializers.DecimalField(**M)
    total_equity = serializers.DecimalField(**M)
    compare_total_assets = serializers.DecimalField(**M)
    compare_total_liabilities = serializers.DecimalField(**M)
    compare_total_equity = serializers.DecimalField(**M)
    balanced = serializers.BooleanField()


class AgedDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    number = serializers.CharField()
    due_date = serializers.DateField()
    days_overdue = serializers.IntegerField()
    amount = serializers.DecimalField(**M)


class AgedBucketsSerializer(serializers.Serializer):
    current = serializers.DecimalField(**M)
    days_1_30 = serializers.DecimalField(**M)
    days_31_60 = serializers.DecimalField(**M)
    days_61_90 = serializers.DecimalField(**M)
    over_90 = serializers.DecimalField(**M)
    total = serializers.DecimalField(**M)


class AgedRowSerializer(AgedBucketsSerializer):
    party_id = serializers.UUIDField()
    name = serializers.CharField()
    documents = AgedDocumentSerializer(many=True)


class AgedReportSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    kind = serializers.CharField()
    rows = AgedRowSerializer(many=True)
    totals = AgedBucketsSerializer()


class VatRowSerializer(serializers.Serializer):
    tax_rate = serializers.CharField()
    rate = serializers.DecimalField(max_digits=6, decimal_places=3)
    net = serializers.DecimalField(**M)
    tax = serializers.DecimalField(**M)


class VatSummarySerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    sales = VatRowSerializer(many=True)
    purchases = VatRowSerializer(many=True)
    output_vat = serializers.DecimalField(**M)
    input_vat = serializers.DecimalField(**M)
    net_vat = serializers.DecimalField(**M)



class PeriodMonthSerializer(serializers.Serializer):
    month = serializers.DateField()
    income = serializers.DecimalField(**M)
    expenses = serializers.DecimalField(**M)
    profit = serializers.DecimalField(**M)


class TopCustomerSerializer(serializers.Serializer):
    name = serializers.CharField()
    amount = serializers.DecimalField(**M)


class TopProductSerializer(serializers.Serializer):
    name = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=18, decimal_places=3)
    amount = serializers.DecimalField(**M)


class PeriodSummarySerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    income = serializers.DecimalField(**M)
    cost_of_sales = serializers.DecimalField(**M)
    expenses = serializers.DecimalField(**M)
    gross_profit = serializers.DecimalField(**M)
    net_profit = serializers.DecimalField(**M)
    cash_in = serializers.DecimalField(**M)
    cash_out = serializers.DecimalField(**M)
    cash_balance = serializers.DecimalField(**M)
    invoiced = serializers.DecimalField(**M)
    invoice_count = serializers.IntegerField()
    cash_sales = serializers.DecimalField(**M)
    cash_sale_count = serializers.IntegerField()
    payments_received = serializers.DecimalField(**M)
    bills = serializers.DecimalField(**M)
    bill_count = serializers.IntegerField()
    spent_on_expenses = serializers.DecimalField(**M)
    payroll_cost = serializers.DecimalField(**M)
    output_vat = serializers.DecimalField(**M)
    input_vat = serializers.DecimalField(**M)
    net_vat = serializers.DecimalField(**M)
    receivables = serializers.DecimalField(**M)
    receivables_overdue = serializers.DecimalField(**M)
    payables = serializers.DecimalField(**M)
    payables_overdue = serializers.DecimalField(**M)
    top_customers = TopCustomerSerializer(many=True)
    top_products = TopProductSerializer(many=True)
    by_month = PeriodMonthSerializer(many=True)


class CategoryRowSerializer(serializers.Serializer):
    category_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    products = serializers.IntegerField()
    stock_value = serializers.DecimalField(**M)
    sales = serializers.DecimalField(**M)
    share = serializers.DecimalField(max_digits=7, decimal_places=2, help_text="Share of the period's sales, in percent")


class CategoryReportSerializer(serializers.Serializer):
    from_date = serializers.DateField()
    to_date = serializers.DateField()
    rows = CategoryRowSerializer(many=True)
    total_sales = serializers.DecimalField(**M)
    total_stock_value = serializers.DecimalField(**M)


class GlanceDocSerializer(serializers.Serializer):
    id = serializers.CharField()
    kind = serializers.CharField()
    number = serializers.CharField()
    party = serializers.CharField()
    date = serializers.DateField()
    days = serializers.IntegerField(help_text="Days until the date; negative is overdue")
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    currency = serializers.CharField()


class GlanceSalesSerializer(serializers.Serializer):
    this_month = serializers.DecimalField(max_digits=18, decimal_places=2)
    last_month = serializers.DecimalField(max_digits=18, decimal_places=2)
    last_month_to_date = serializers.DecimalField(max_digits=18, decimal_places=2)
    change_percent = serializers.FloatField(allow_null=True)
    collected = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)
    month_label = serializers.CharField()
    last_month_label = serializers.CharField()


class GlanceQuotesSerializer(serializers.Serializer):
    open_count = serializers.IntegerField()
    open_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    sent_count = serializers.IntegerField()
    draft_count = serializers.IntegerField()
    to_review_count = serializers.IntegerField()
    expiring_count = serializers.IntegerField()
    expiring_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    accepted_count = serializers.IntegerField()
    accepted_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    list = GlanceDocSerializer(many=True)


class GlanceDebtorSerializer(serializers.Serializer):
    name = serializers.CharField()
    amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    count = serializers.IntegerField()


class GlanceOwedSerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=18, decimal_places=2)
    count = serializers.IntegerField()
    overdue = serializers.DecimalField(max_digits=18, decimal_places=2)
    overdue_count = serializers.IntegerField()
    due_soon = serializers.DecimalField(max_digits=18, decimal_places=2)
    due_soon_count = serializers.IntegerField()
    draft_count = serializers.IntegerField()
    list = GlanceDocSerializer(many=True)


class GlanceReceivablesSerializer(GlanceOwedSerializer):
    top_overdue = GlanceDebtorSerializer(many=True)


class GlancePayablesSerializer(GlanceOwedSerializer):
    vouchers_waiting = serializers.IntegerField(allow_null=True)
    vouchers_waiting_value = serializers.DecimalField(max_digits=18, decimal_places=2, allow_null=True)


class GlanceCashAccountSerializer(serializers.Serializer):
    name = serializers.CharField()
    balance = serializers.DecimalField(max_digits=18, decimal_places=2)


class GlanceCashSerializer(serializers.Serializer):
    total = serializers.DecimalField(max_digits=18, decimal_places=2)
    accounts = GlanceCashAccountSerializer(many=True)


class GlanceSerializer(serializers.Serializer):
    """Each part is null when the person may not see it."""

    today = serializers.DateField()
    sales = GlanceSalesSerializer(allow_null=True)
    quotes = GlanceQuotesSerializer(allow_null=True)
    receivables = GlanceReceivablesSerializer(allow_null=True)
    payables = GlancePayablesSerializer(allow_null=True)
    cash = GlanceCashSerializer(allow_null=True)
