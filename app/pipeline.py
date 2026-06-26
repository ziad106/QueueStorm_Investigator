"""Orchestrates: engine -> text -> optional LLM -> safety -> validated output."""
from .schemas import TicketOut
from . import engine, textgen, safety, llm


def analyze(ticket) -> TicketOut:
    dec = engine.investigate(ticket)
    summary, action, reply = textgen.build_text(ticket, dec)
    summary, action, reply = llm.enhance(ticket, dec, summary, action, reply)
    # Deterministic safety filter is ALWAYS the last word, even over LLM output.
    reply = safety.sanitize_reply(reply)
    action = safety.sanitize_action(action)
    return TicketOut(
        ticket_id=ticket.ticket_id,
        relevant_transaction_id=dec["relevant_transaction_id"],
        evidence_verdict=dec["evidence_verdict"],
        case_type=dec["case_type"],
        severity=dec["severity"],
        department=dec["department"],
        agent_summary=summary,
        recommended_next_action=action,
        customer_reply=reply,
        human_review_required=dec["human_review_required"],
        confidence=dec["confidence"],
        reason_codes=dec["reason_codes"],
    )


def safe_fallback(ticket_id) -> TicketOut:
    """Last-resort valid response so an unexpected error never yields a 5xx/crash."""
    return TicketOut(
        ticket_id=ticket_id or "unknown",
        relevant_transaction_id=None,
        evidence_verdict="insufficient_data",
        case_type="other",
        severity="low",
        department="customer_support",
        agent_summary="The ticket could not be fully analyzed automatically and needs manual review.",
        recommended_next_action="Route to customer_support for manual review of the ticket details.",
        customer_reply=(
            "Thank you for reaching out. Our team will review your request and contact you through "
            "official support channels. Please do not share your PIN or OTP with anyone."
        ),
        human_review_required=True,
        confidence=0.3,
        reason_codes=["manual_review", "automatic_analysis_unavailable"],
    )
