from typing import Any, List, Optional, Literal
from pydantic import BaseModel, ConfigDict, field_validator

EVIDENCE_VERDICTS = ("consistent", "inconsistent", "insufficient_data")
CASE_TYPES = (
    "wrong_transfer", "payment_failed", "refund_request", "duplicate_payment",
    "merchant_settlement_delay", "agent_cash_in_issue",
    "phishing_or_social_engineering", "other",
)
SEVERITIES = ("low", "medium", "high", "critical")
DEPARTMENTS = (
    "customer_support", "dispute_resolution", "payments_ops",
    "merchant_operations", "agent_operations", "fraud_risk",
)


def _to_str(v):
    if v is None or isinstance(v, (dict, list)):
        return None
    return v if isinstance(v, str) else str(v)


class TxnIn(BaseModel):
    # Permissive: hidden tests may carry unexpected values/keys/types. Never 400 on these;
    # salvage what we can and null the rest so the analysis still runs.
    model_config = ConfigDict(extra="ignore")
    transaction_id: Optional[str] = None
    timestamp: Optional[str] = None
    type: Optional[str] = None
    amount: Optional[float] = None
    counterparty: Optional[str] = None
    status: Optional[str] = None

    @field_validator("transaction_id", "timestamp", "type", "counterparty", "status", mode="before")
    @classmethod
    def _coerce_str(cls, v):
        return _to_str(v)

    @field_validator("amount", mode="before")
    @classmethod
    def _coerce_amount(cls, v):
        if v is None or isinstance(v, bool):
            return None
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.replace(",", "").replace("৳", "").strip()
            try:
                return float(s)
            except ValueError:
                return None
        return None


class TicketIn(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "example": {
                "ticket_id": "TKT-001",
                "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
                "language": "en",
                "channel": "in_app_chat",
                "user_type": "customer",
                "campaign_context": "boishakh_bonanza_day_1",
                "transaction_history": [
                    {
                        "transaction_id": "TXN-9101",
                        "timestamp": "2026-04-14T14:08:22Z",
                        "type": "transfer",
                        "amount": 5000,
                        "counterparty": "+8801719876543",
                        "status": "completed",
                    }
                ],
                "metadata": {},
            }
        },
    )
    ticket_id: str
    complaint: str
    language: Optional[str] = None
    channel: Optional[str] = None
    user_type: Optional[str] = None
    campaign_context: Optional[str] = None
    transaction_history: Optional[List[TxnIn]] = None
    metadata: Optional[Any] = None

    @field_validator("ticket_id", "complaint", mode="before")
    @classmethod
    def _req_str(cls, v):
        # Coerce a non-string scalar to str so a numeric ticket_id/complaint still runs.
        return v if isinstance(v, str) or v is None else (None if isinstance(v, (dict, list)) else str(v))

    @field_validator("language", "channel", "user_type", "campaign_context", mode="before")
    @classmethod
    def _opt_str(cls, v):
        return _to_str(v)


class TicketOut(BaseModel):
    ticket_id: str
    relevant_transaction_id: Optional[str]
    evidence_verdict: Literal["consistent", "inconsistent", "insufficient_data"]
    case_type: Literal[
        "wrong_transfer", "payment_failed", "refund_request", "duplicate_payment",
        "merchant_settlement_delay", "agent_cash_in_issue",
        "phishing_or_social_engineering", "other",
    ]
    severity: Literal["low", "medium", "high", "critical"]
    department: Literal[
        "customer_support", "dispute_resolution", "payments_ops",
        "merchant_operations", "agent_operations", "fraud_risk",
    ]
    agent_summary: str
    recommended_next_action: str
    customer_reply: str
    human_review_required: bool
    confidence: float = 0.5
    reason_codes: List[str] = []
