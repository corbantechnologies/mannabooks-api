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
