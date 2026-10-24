from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.plans.views import PublicPlanListView


def health(_request):
    return JsonResponse({"status": "ok"})


# Workspace-scoped apps: every URL starts with /api/v1/w/<workspace slug>/
workspace_patterns = [
    path("", include("apps.workspaces.urls_scoped")),
    path("branches/", include("apps.branches.urls")),
    path("roles/", include("apps.roles.urls")),
    path("members/", include("apps.memberships.urls")),
    path("invitations/", include("apps.invitations.urls")),
    path("departments/", include("apps.departments.urls")),
    path("employees/", include("apps.employees.urls")),
    path("sequences/", include("apps.sequences.urls")),
    path("audit-logs/", include("apps.auditlogs.urls")),
    path("currencies/", include("apps.currencies.urls")),
    path("exchange-rates/", include("apps.exchangerates.urls")),
    path("tax-rates/", include("apps.taxrates.urls")),
    path("ledger-accounts/", include("apps.ledgeraccounts.urls")),
    path("journals/", include("apps.journals.urls")),
    path("fiscal-years/", include("apps.fiscalyears.urls")),
    path("periods/", include("apps.periods.urls")),
    path("opening-balances/", include("apps.openingbalances.urls")),
    path("reports/", include("apps.reports.urls")),
    path("customers/", include("apps.customers.urls")),
    path("products/", include("apps.products.urls")),
    path("product-categories/", include("apps.productcategories.urls")),
    path("units/", include("apps.units.urls")),
    path("price-lists/", include("apps.pricelists.urls")),
    path("quotations/", include("apps.quotations.urls")),
    path("catalogues/", include("apps.catalogues.urls")),
    path("invoices/", include("apps.invoices.urls")),
    path("payments/", include("apps.payments.urls")),
    path("receipts/", include("apps.receipts.urls")),
    path("credit-notes/", include("apps.creditnotes.urls")),
    path("suppliers/", include("apps.suppliers.urls")),
    path("warehouses/", include("apps.warehouses.urls")),
    path("stock/", include("apps.stockmovements.urls")),
    path("purchase-orders/", include("apps.purchaseorders.urls")),
    path("service-orders/", include("apps.serviceorders.urls")),
    path("service-completions/", include("apps.servicecompletions.urls")),
    path("goods-receipts/", include("apps.goodsreceipts.urls")),
    path("bills/", include("apps.bills.urls")),
    path("supplier-payments/", include("apps.supplierpayments.urls")),
    path("payment-vouchers/", include("apps.paymentvouchers.urls")),
    path("stock-transfers/", include("apps.stocktransfers.urls")),
    path("stock-adjustments/", include("apps.stockadjustments.urls")),
    path("stock-takes/", include("apps.stocktakes.urls")),
    path("bills-of-materials/", include("apps.billsofmaterials.urls")),
    path("production-orders/", include("apps.productionorders.urls")),
    path("bank-accounts/", include("apps.bankaccounts.urls")),
    path("expenses/", include("apps.expenses.urls")),
    path("other-income/", include("apps.otherincomes.urls")),
    path("bank-transfers/", include("apps.banktransfers.urls")),
    path("statement-lines/", include("apps.bankstatementlines.urls")),
    path("reconciliations/", include("apps.reconciliations.urls")),
    path("statutory-rates/", include("apps.statutoryrates.urls")),
    path("leave-requests/", include("apps.leaverequests.urls")),
    path("pay-runs/", include("apps.payruns.urls")),
    path("payslips/", include("apps.payslips.urls")),
    path("cost-centers/", include("apps.costcenters.urls")),
    path("projects/", include("apps.projects.urls")),
    path("budgets/", include("apps.budgets.urls")),
    path("approval-rules/", include("apps.approvalrules.urls")),
    path("approvals/", include("apps.approvalrequests.urls")),
    path("fixed-assets/", include("apps.fixedassets.urls")),
    path("depreciation/", include("apps.depreciationentries.urls")),
    path("report-submissions/", include("apps.reportsubmissions.urls")),
    path("report-requests/", include("apps.reportsubmissions.urls_requests")),
    path("payment-options/", include("apps.paymentoptions.urls")),
    path("leads/", include("apps.leads.urls")),
    path("deals/", include("apps.deals.urls")),
    path("activities/", include("apps.activities.urls")),
    path("inbox/", include("apps.inboxmessages.urls")),
    path("online-orders/", include("apps.onlineorders.urls")),
    path("billing/", include("apps.subscriptions.urls")),
    path("support/", include("apps.supporttickets.urls")),
    path("", include("apps.importjobs.urls")),  # imports/ and exports/
    path("document-emails/", include("apps.documentemails.urls")),
    path("related-documents/", include("apps.relateddocs.urls")),
    path("delivery-notes/", include("apps.deliverynotes.urls")),
    path("recurring-invoices/", include("apps.recurringinvoices.urls")),
    path("reminders/", include("apps.reminders.urls")),
    path("mpesa/connection/", include("apps.mpesaconnections.urls")),
    path("mpesa/transactions/", include("apps.mpesatransactions.urls")),
    path("pos/registers/", include("apps.posregisters.urls")),
    path("pos/shifts/", include("apps.posshifts.urls")),
    path("loyalty/program/", include("apps.loyaltyprograms.urls")),
    path("loyalty/tiers/", include("apps.loyaltytiers.urls")),
    path("loyalty/members/", include("apps.loyaltymembers.urls")),
    path("loyalty/transactions/", include("apps.loyaltytransactions.urls")),
    path("portal-links/", include("apps.portallinks.urls")),
    path("etims/device/", include("apps.etimsdevices.urls")),
    path("etims/submissions/", include("apps.etimssubmissions.urls")),
]

urlpatterns = [
    path("health/", health),
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/workspaces/", include("apps.workspaces.urls")),
    path("api/v1/groups/", include("apps.companygroups.urls")),
    path("api/v1/platform/", include("apps.platform.urls")),  # MannaBooks staff
    path("api/v1/plans/", PublicPlanListView.as_view(), name="public-plans"),
    path("api/v1/invitations/", include("apps.invitations.urls_public")),
    path("api/v1/hooks/pay/", include("apps.mpesatransactions.urls_hooks")),  # Safaricom callbacks
    path("api/v1/portal/", include("apps.portallinks.urls_public")),  # customers, no sign-in
    path("api/v1/store/", include("apps.onlineorders.urls_public")),  # the public online shop
    path("api/v1/shared/", include("apps.catalogues.urls_public")),  # shared catalogues and quote links
    path("api/v1/w/<slug:workspace>/", include(workspace_patterns)),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/v1/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="api-docs"),
]
