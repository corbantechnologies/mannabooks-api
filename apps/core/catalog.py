"""
Permission catalogue. Permissions are written `module.action`; a role holds a list of them.
`*` grants everything and `module.*` grants every action in one module. Each new module adds its
entry here, and preset roles are updated in the same change.
"""

MODULES: dict[str, dict] = {
    "workspace": {"label": "Workspace settings", "actions": ["view", "manage"]},
    "branches": {"label": "Branches", "actions": ["view", "manage"]},
    "roles": {"label": "Roles", "actions": ["view", "manage"]},
    "members": {"label": "Team members", "actions": ["view", "manage"]},
    "invitations": {"label": "Invitations", "actions": ["view", "manage"]},
    "departments": {"label": "Departments", "actions": ["view", "manage"]},
    "employees": {"label": "Employees", "actions": ["view", "manage", "view_own"]},
    "sequences": {"label": "Document numbering", "actions": ["view", "manage"]},
    "auditlogs": {"label": "Audit log", "actions": ["view"]},
    # Phase 1: accounting core
    "ledgeraccounts": {"label": "Chart of accounts", "actions": ["view", "manage"]},
    "journals": {"label": "Journal entries", "actions": ["view", "create", "post", "reverse"]},
    "fiscalyears": {"label": "Financial years", "actions": ["view", "manage"]},
    "periods": {"label": "Accounting periods", "actions": ["view", "manage"]},
    "currencies": {"label": "Currencies and exchange rates", "actions": ["view", "manage"]},
    "taxrates": {"label": "Tax rates", "actions": ["view", "manage"]},
    "openingbalances": {"label": "Opening balances", "actions": ["view", "manage"]},
    "reports": {"label": "Financial reports", "actions": ["view"]},
    # Phase 2: sales
    "customers": {"label": "Customers", "actions": ["view", "manage"]},
    "products": {"label": "Products and services", "actions": ["view", "manage"]},
    "quotations": {"label": "Quotations", "actions": ["view", "manage"]},
    "invoices": {"label": "Invoices", "actions": ["view", "create", "issue", "void"]},
    "payments": {"label": "Customer payments", "actions": ["view", "create", "void"]},
    "receipts": {"label": "Cash sales", "actions": ["view", "create", "void"]},
    "creditnotes": {"label": "Credit notes", "actions": ["view", "create", "void"]},
    "deliverynotes": {"label": "Delivery notes", "actions": ["view", "manage"]},
    "recurringinvoices": {"label": "Recurring invoices", "actions": ["view", "manage"]},
    "reminders": {"label": "Payment reminders", "actions": ["view", "manage"]},
    "mpesa": {"label": "M-Pesa connection", "actions": ["view", "manage"]},
    "pos": {"label": "Point of sale", "actions": ["view", "sell", "manage"]},
    "loyalty": {"label": "Loyalty programme", "actions": ["view", "enrol", "manage"]},
    # Phase 3: purchasing and stock
    "suppliers": {"label": "Suppliers", "actions": ["view", "manage"]},
    "purchaseorders": {"label": "Purchase and service orders", "actions": ["view", "create", "approve"]},
    "goodsreceipts": {"label": "Goods received", "actions": ["view", "manage"]},
    "bills": {"label": "Supplier bills", "actions": ["view", "create", "post", "void"]},
    "paymentvouchers": {"label": "Payment vouchers", "actions": ["view", "create", "approve"]},
    "supplierpayments": {"label": "Supplier payments", "actions": ["view", "create", "void"]},
    "inventory": {"label": "Inventory", "actions": ["view", "manage"]},
    "manufacturing": {"label": "Manufacturing", "actions": ["view", "manage"]},
    # Phase 4: cash and banking
    "banking": {"label": "Cash and banking", "actions": ["view", "spend", "receive", "transfer", "reconcile"]},
    # Phase 5: people
    "leave": {"label": "Leave", "actions": ["request", "view", "approve"]},
    "payroll": {"label": "Payroll", "actions": ["view", "manage", "approve"]},
    # Phase 6: control and reporting
    "budgets": {"label": "Budgets and cost centres", "actions": ["view", "manage", "approve"]},
    "projects": {"label": "Projects", "actions": ["view", "manage"]},
    "approvals": {"label": "Approval rules and requests", "actions": ["view", "manage"]},
    "fixedassets": {"label": "Fixed assets", "actions": ["view", "manage", "depreciate"]},
    "workreports": {"label": "Work reports", "actions": ["request", "view", "manage"]},
    "etims": {"label": "KRA eTIMS", "actions": ["view", "manage"]},
}

# Modules a department can run (its head becomes their in-charge). Grows with each phase.
DEPARTMENT_MODULES: dict[str, str] = {
    "sales": "Sales and invoicing",
    "purchasing": "Purchasing",
    "inventory": "Inventory and stores",
    "finance": "Finance and accounting",
    "banking": "Cash and banking",
    "hr": "HR and payroll",
    "crm": "CRM",
    "projects": "Projects",
}

_VIEW_BASICS = ["workspace.view", "branches.view", "departments.view", "employees.view_own", "leave.request", "workreports.request"]
# What every trading role needs to price and record sales and purchases.
_TRADING_LOOKUPS = ["currencies.view", "taxrates.view"]
_SELLING = [
    "customers.*", "products.view", "quotations.*", "invoices.view", "invoices.create", "invoices.issue",
    "payments.view", "payments.create", "receipts.view", "receipts.create", "creditnotes.view",
    "deliverynotes.*", "recurringinvoices.view", "reminders.view", "loyalty.view", "loyalty.enrol", "inventory.view", "projects.view",
]
_ACCOUNTING = [
    "ledgeraccounts.*", "journals.*", "fiscalyears.*", "periods.*", "currencies.*", "taxrates.*",
    "openingbalances.*", "reports.*", "customers.*", "products.*", "quotations.*", "invoices.*", "payments.*",
    "receipts.*", "creditnotes.*", "etims.*",
    "deliverynotes.*", "recurringinvoices.*", "reminders.*", "mpesa.*", "pos.*", "loyalty.*",
    "suppliers.*", "purchaseorders.view", "goodsreceipts.view", "bills.*", "paymentvouchers.*", "supplierpayments.*", "inventory.view",
    "manufacturing.view", "banking.*", "payroll.view", "payroll.approve",
    "budgets.view", "budgets.manage", "projects.*", "approvals.view", "fixedassets.*",
]

PRESET_ROLES: list[dict] = [
    {"slug": "owner", "name": "Owner", "description": "Full access, including billing and deleting the workspace.", "permissions": ["*"]},
    {"slug": "admin", "name": "Admin", "description": "Full access to every module.", "permissions": ["*"]},
    {
        "slug": "accountant",
        "name": "Accountant",
        "description": "Finance, banking and reports.",
        "permissions": _VIEW_BASICS + _ACCOUNTING + ["employees.view", "auditlogs.view", "sequences.view"],
    },
    {"slug": "sales", "name": "Sales", "description": "Customers, quotations, invoices and payments.", "permissions": _VIEW_BASICS + _TRADING_LOOKUPS + _SELLING},
    {
        "slug": "cashier",
        "name": "Cashier",
        "description": "Point of sale and cash receipts.",
        "permissions": _VIEW_BASICS + _TRADING_LOOKUPS + ["customers.view", "products.view", "receipts.view", "receipts.create", "payments.view",
                                                         "payments.create", "pos.view", "pos.sell", "loyalty.view", "loyalty.enrol", "inventory.view",
                                                         "banking.spend"],
    },
    {"slug": "store-manager", "name": "Store manager", "description": "Stock, warehouses and purchasing.", "permissions": _VIEW_BASICS + _TRADING_LOOKUPS + [
        "products.*", "customers.view", "suppliers.*", "purchaseorders.view", "purchaseorders.create", "goodsreceipts.*", "bills.view",
        "inventory.*", "manufacturing.*", "deliverynotes.*",
    ]},
    {
        "slug": "hr-manager",
        "name": "HR manager",
        "description": "Employees, departments, leave and payroll.",
        "permissions": _VIEW_BASICS + ["employees.*", "departments.*", "invitations.view", "members.view", "leave.*", "payroll.view", "payroll.manage", "workreports.*"],
    },
    {
        "slug": "self-service",
        "name": "Self-service",
        "description": "An employee's own payslips, leave and profile.",
        "permissions": ["workspace.view", "employees.view_own", "leave.request"],
    },
]


def all_permission_codes() -> list[str]:
    return [f"{module}.{action}" for module, spec in MODULES.items() for action in spec["actions"]]


def is_valid_code(code: str) -> bool:
    if code == "*":
        return True
    module, _, action = code.partition(".")
    if module not in MODULES:
        return False
    return action == "*" or action in MODULES[module]["actions"]


def grants(held: list[str], code: str) -> bool:
    """Whether a list of held permissions grants `code`."""
    module = code.split(".", 1)[0]
    return "*" in held or code in held or f"{module}.*" in held


# Parts of MannaBooks a workspace can switch on and off (accounting, reports and the organisation are always on).
APP_MODULES: dict[str, dict] = {
    "sales": {"label": "Sales and invoicing", "description": "Customers, quotations, invoices, payments, credit notes, delivery notes."},
    "pos": {"label": "Point of sale", "description": "The till with shifts, cash counts and loyalty points."},
    "purchasing": {"label": "Purchasing", "description": "Suppliers, LPOs, goods received, bills and supplier payments."},
    "inventory": {"label": "Stock and warehouses", "description": "Stock levels, warehouses, transfers, adjustments and stock takes."},
    "manufacturing": {"label": "Manufacturing", "description": "Recipes and production."},
    "banking": {"label": "Cash and banking", "description": "Bank, M-Pesa and cash accounts, expenses and reconciliation."},
    "people": {"label": "Leave and payroll", "description": "Leave, payroll with PAYE, SHIF, NSSF and Housing Levy, payslips, work reports."},
    "projects": {"label": "Projects", "description": "Job costing: income, costs and profit per job or contract."},
    "control": {"label": "Budgets, approvals and assets", "description": "Budgets, cost centres, approval chains and fixed assets."},
}

# What a new business wants to do first; each switches on the modules it needs (changeable any time in Settings).
GOALS: dict[str, dict] = {
    "invoicing": {"label": "Send invoices and get paid", "description": "For service businesses, consultants and freelancers.",
                  "modules": ["sales", "banking"]},
    "shop": {"label": "Run a shop with a till", "description": "Retail shops, chemists, hardware stores, restaurants and bars.",
             "modules": ["sales", "pos", "inventory", "purchasing", "banking"]},
    "stock": {"label": "Manage stock and warehouses", "description": "Distributors and stores that mainly track goods.",
              "modules": ["inventory", "purchasing"]},
    "projects": {"label": "Run jobs and projects", "description": "Contractors, agencies, law and consulting firms.",
                 "modules": ["sales", "purchasing", "banking", "projects"]},
    "manufacturing": {"label": "Make products", "description": "Bakeries, factories, workshops.",
                      "modules": ["sales", "purchasing", "inventory", "manufacturing", "banking"]},
    "payroll": {"label": "Run payroll", "description": "Pay staff with PAYE, SHIF, NSSF and the Housing Levy done for you.",
                "modules": ["people", "banking"]},
    "everything": {"label": "Everything", "description": "The full system: every module switched on.", "modules": list(APP_MODULES)},
}
