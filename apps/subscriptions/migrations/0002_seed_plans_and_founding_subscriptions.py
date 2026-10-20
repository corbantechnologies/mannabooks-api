import random
from decimal import Decimal

from django.db import migrations

ALL = ["sales", "pos", "store", "purchasing", "inventory", "manufacturing", "banking", "people", "projects", "crm", "control"]
PLANS = [
    # key, name, description, monthly, yearly, modules, features, users, documents, payroll per employee, payroll minimum, free, sort
    ("free", "Free", "Invoices, cash sales and M-Pesa for one person starting out.", 0, 0, ["sales", "banking"], [], 1, 30, 0, 0, True, 0),
    ("biashara", "Biashara", "Service businesses: sales, banking, VAT, CRM and payroll.", 1500, 15000, ["sales", "banking", "crm", "people", "projects"],
     ["business_inbox"], 3, None, 100, 500, False, 1),
    ("duka", "Duka", "Shops, restaurants and stores: the till, stock, buying, recipes and an online shop.", 3500, 35000,
     ["sales", "pos", "store", "purchasing", "inventory", "manufacturing", "banking", "crm", "people", "projects"], ["business_inbox"], 5, None, 100, 500,
     False, 2),
    ("kampuni", "Kampuni", "Growing and multi-branch firms: everything, with budgets, approvals, assets and company groups.", 8000, 80000, ALL,
     ["business_inbox", "company_groups"], 15, None, 100, 500, False, 3),
]


def seed(apps, schema_editor):
    Plan = apps.get_model("plans", "Plan")
    Subscription = apps.get_model("subscriptions", "Subscription")
    Workspace = apps.get_model("workspaces", "Workspace")
    plans = {}
    for key, name, desc, monthly, yearly, modules, features, users, docs, per_emp, minimum, free, sort in PLANS:
        plans[key], _ = Plan.objects.get_or_create(key=key, defaults={
            "name": name, "description": desc, "price_monthly": Decimal(monthly), "price_yearly": Decimal(yearly), "modules": modules,
            "features": features, "max_users": users, "max_documents_month": docs, "payroll_per_employee": Decimal(per_emp),
            "payroll_minimum": Decimal(minimum), "is_free": free, "sort": sort,
        })
    taken = set(Subscription.objects.values_list("account_number", flat=True))
    for ws in Workspace.objects.filter(subscription__isnull=True):
        number = f"MB{random.randint(100000, 999999)}"
        while number in taken:
            number = f"MB{random.randint(100000, 999999)}"
        taken.add(number)
        # businesses here before billing are the pilot's founding businesses: free until MannaBooks launches
        Subscription.objects.create(workspace=ws, plan=plans["kampuni"], status="active", complimentary=True, account_number=number,
                                    notes="Founding (pilot) business: free until launch, then 50% off for the first year.")


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0001_initial"), ("plans", "0001_initial"), ("workspaces", "0005_workspace_blocked_at_workspace_blocked_reason")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
