from django.db import transaction

from apps.core.exceptions import BusinessRuleError
from apps.sequences.services import next_value

from .models import Lead


@transaction.atomic
def convert(lead: Lead, *, customer=None, deal_title: str = "", deal_value=None, user=None) -> dict:
    """
    Make the lead a customer (a new one from its details, or one chosen), and optionally open a deal for it.
    Its activities move to the customer so the history stays together.
    """
    from apps.customers.models import Customer
    from apps.deals.models import Deal

    if lead.status == Lead.Status.CONVERTED:
        raise BusinessRuleError("This lead is already a customer.")
    if lead.status == Lead.Status.LOST:
        raise BusinessRuleError("This lead was marked lost. Reopen it first.")
    if customer is None:
        customer = Customer.objects.create(
            workspace=lead.workspace, created_by=user, number=next_value(lead.workspace, "customer"),
            name=lead.company or lead.name, kind=Customer.Kind.COMPANY if lead.company else Customer.Kind.INDIVIDUAL,
            email=lead.email, phone=lead.phone, notes=f"Contact: {lead.name}" if lead.company else "",
        )
    elif customer.workspace_id != lead.workspace_id:
        raise BusinessRuleError("That customer belongs to another workspace.")
    lead.customer, lead.status = customer, Lead.Status.CONVERTED
    lead.save(update_fields=["customer", "status", "updated_at"])
    lead.activities.update(customer=customer)
    deal = None
    if deal_title.strip():
        deal = Deal.objects.create(
            workspace=lead.workspace, created_by=user, number=next_value(lead.workspace, "deal"), title=deal_title.strip()[:200],
            customer=customer, lead=lead, stage=Deal.Stage.QUALIFIED, value=deal_value if deal_value is not None else lead.estimated_value,
            assigned_to=lead.assigned_to,
        )
    return {"lead": lead, "customer": customer, "deal": deal}


def mark_lost(lead: Lead, reason: str) -> Lead:
    if lead.status == Lead.Status.CONVERTED:
        raise BusinessRuleError("This lead is already a customer.")
    lead.status, lead.lost_reason = Lead.Status.LOST, reason.strip()[:255]
    lead.save(update_fields=["status", "lost_reason", "updated_at"])
    return lead


def reopen(lead: Lead) -> Lead:
    if lead.status != Lead.Status.LOST:
        raise BusinessRuleError("Only a lost lead can be reopened.")
    lead.status, lead.lost_reason = Lead.Status.CONTACTED, ""
    lead.save(update_fields=["status", "lost_reason", "updated_at"])
    return lead
