from rest_framework import serializers

from .models import Payslip


class PayItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    kind = serializers.ChoiceField(choices=["earning", "deduction"])
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=0)
    taxable = serializers.BooleanField(default=True)


class PayslipSerializer(serializers.ModelSerializer):
    items = PayItemSerializer(many=True, required=False)
    period = serializers.SerializerMethodField()
    pay_run_status = serializers.CharField(source="pay_run.status", read_only=True)
    pay_date = serializers.DateField(source="pay_run.pay_date", read_only=True)
    department = serializers.CharField(source="employee.department.name", read_only=True, default=None)
    job_title = serializers.CharField(source="employee.job_title", read_only=True)
    nssf_number = serializers.CharField(source="employee.nssf_number", read_only=True)
    shif_number = serializers.CharField(source="employee.shif_number", read_only=True)

    class Meta:
        model = Payslip
        fields = ["id", "pay_run", "period", "pay_run_status", "pay_date", "employee", "employee_name", "staff_number", "kra_pin", "department",
                  "job_title", "nssf_number", "shif_number", "basic_salary", "unpaid_leave_days", "unpaid_leave_deduction", "items", "gross_pay",
                  "taxable_pay", "nssf_employee", "nssf_employer", "shif", "housing_levy_employee", "housing_levy_employer", "paye_before_relief",
                  "personal_relief", "paye", "other_deductions", "net_pay", "pay_method", "pay_to"]
        read_only_fields = [f for f in fields if f not in ("basic_salary", "unpaid_leave_days", "items")]

    def get_period(self, obj) -> str:
        import calendar

        return f"{calendar.month_name[obj.pay_run.month]} {obj.pay_run.year}"

    def validate_items(self, items):
        return [{**i, "amount": float(i["amount"])} for i in items]  # stored as JSON

    def to_representation(self, instance):
        data = super().to_representation(instance)
        for item in data.get("items") or []:
            item["amount"] = str(item["amount"])
        return data
