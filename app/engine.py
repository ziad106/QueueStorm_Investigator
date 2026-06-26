"""Deterministic investigation engine.

Owns every scored decision field: relevant_transaction_id, evidence_verdict,
case_type, department, severity, human_review_required, confidence, reason_codes.
The LLM (if enabled) only rewrites the three free-text fields, never these.
"""
from . import extract as ex

AMOUNT, TYPE, CP, TIME, STATUS = 5.0, 4.0, 3.0, 3.0, 2.0

# case_type -> (department, expected txn type, expected txn status, base severity)
CASE_MAP = {
    "wrong_transfer": ("dispute_resolution", "transfer", "completed", "medium"),
    "payment_failed": ("payments_ops", "payment", "failed", "high"),
    "refund_request": ("customer_support", "payment", "completed", "low"),
    "duplicate_payment": ("payments_ops", "payment", "completed", "high"),
    "merchant_settlement_delay": ("merchant_operations", "settlement", "pending", "medium"),
    "agent_cash_in_issue": ("agent_operations", "cash_in", "pending", "high"),
    "phishing_or_social_engineering": ("fraud_risk", None, None, "critical"),
    "other": ("customer_support", None, None, "low"),
}
SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}
HIGH_VALUE = 50000.0


SEND_HINTS = ["sent", "send", "transfer", "transferred", "pathiyechi", "pathalam",
              "পাঠিয়েছি", "পাঠিয়েছ", "পাঠালাম", "দিয়েছি", "পাঠাই"]


def _mentions_send(complaint):
    t = complaint.lower()
    return any(h in t for h in SEND_HINTS)


def classify(complaint, user_type):
    """Keyword priority classification. Complaint is untrusted data."""
    if ex.is_phishing(complaint):
        return "phishing_or_social_engineering"
    if ex.has_kw(complaint, "duplicate"):
        return "duplicate_payment"
    if ex.has_kw(complaint, "failed"):
        return "payment_failed"
    if ex.has_kw(complaint, "agent_cash_in") and (
        ex.has_kw(complaint, "not_received") or "balance" in complaint.lower() or "ব্যালেন্স" in complaint
    ):
        return "agent_cash_in_issue"
    if (user_type == "merchant" or ex.has_kw(complaint, "settlement")) and ex.has_kw(complaint, "settlement"):
        return "merchant_settlement_delay"
    if ex.has_kw(complaint, "wrong_transfer"):
        return "wrong_transfer"
    if ex.has_kw(complaint, "not_received") and _mentions_send(complaint):
        return "wrong_transfer"
    if ex.has_kw(complaint, "refund"):
        return "refund_request"
    if ex.has_kw(complaint, "agent_cash_in"):
        return "agent_cash_in_issue"
    return "other"


def _norm_digits(s):
    import re
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if d else ""


def score_txn(tx, feats, exp_type, exp_status):
    s, codes = 0.0, []
    amt = tx.amount
    if amt is not None and feats["amounts"]:
        if any(abs(amt - a) < 0.5 for a in feats["amounts"]):
            s += AMOUNT
            codes.append("amount_match")
    if exp_type and tx.type == exp_type:
        s += TYPE
        codes.append("type_match")
    if tx.counterparty:
        cp_digits = _norm_digits(tx.counterparty)
        if (cp_digits and cp_digits in feats["phones"]) or tx.counterparty in feats["ids"]:
            s += CP
            codes.append("counterparty_match")
    d = ex.parse_ts(tx.timestamp)
    if d and feats["ref_today"] is not None and feats["day_offset"] is not None:
        from datetime import timedelta
        target = (feats["ref_today"] + timedelta(days=feats["day_offset"])).date()
        if d.date() == target:
            if feats["hour"] is not None and abs(d.hour - feats["hour"]) <= 2:
                s += TIME
                codes.append("timestamp_match")
            else:
                s += TIME - 1
                codes.append("date_match")
    if exp_status and tx.status == exp_status:
        s += STATUS
        codes.append("status_" + tx.status)
    return s, codes


def find_duplicate(txns):
    """Return (later_txn, earlier_txn) if a near-identical pair exists."""
    from datetime import timedelta
    for i in range(len(txns)):
        for j in range(i + 1, len(txns)):
            a, b = txns[i], txns[j]
            if (a.amount is not None and a.amount == b.amount and a.amount > 0
                    and a.counterparty == b.counterparty and a.type == b.type
                    and (a.status in ("completed", None)) and (b.status in ("completed", None))):
                da, db = ex.parse_ts(a.timestamp), ex.parse_ts(b.timestamp)
                if da and db and abs((da - db).total_seconds()) <= 3600:
                    return (a, b) if da >= db else (b, a)
                return (a, b)
    return None


def _status_contradicts(case, tx):
    """True when the matched transaction's status contradicts the complaint."""
    if tx is None:
        return False
    s = tx.status
    if case == "payment_failed":
        return s == "completed"            # claimed failed, but it actually completed
    if case == "merchant_settlement_delay":
        return s in ("completed", "reversed")   # claimed delayed, but already settled
    if case == "agent_cash_in_issue":
        return s == "reversed"             # claimed not received, but it was reversed
    return False


def established_recipient(tx, txns):
    if not tx or not tx.counterparty:
        return False
    n = sum(1 for t in txns if t.counterparty == tx.counterparty and t.type == "transfer")
    return n >= 2


def investigate(ticket):
    complaint = ticket.complaint or ""
    txns = ticket.transaction_history or []
    feats = ex.extract_features(complaint, ticket.language, txns)
    case = classify(complaint, ticket.user_type)
    dept, exp_type, exp_status, base_sev = CASE_MAP[case]

    relevant, verdict, codes = None, "insufficient_data", [case]
    best_tx = None
    confidence = 0.6

    if case == "phishing_or_social_engineering":
        verdict, relevant = "insufficient_data", None
        codes += ["phishing_detected", "credential_protection"]
        confidence = 0.95

    elif case == "duplicate_payment":
        dup = find_duplicate(txns)
        if dup:
            later, _earlier = dup
            relevant, best_tx, verdict = later.transaction_id, later, "consistent"
            codes += ["duplicate_candidate", "amount_match", "biller_verification_required"]
            confidence = 0.9
        else:
            # Customer claims a duplicate but no second matching charge exists ->
            # cannot confirm from the evidence. Do not guess; flag insufficient.
            relevant, verdict = None, "insufficient_data"
            codes += ["duplicate_unconfirmed", "needs_clarification"]
            confidence = 0.55

    else:
        best_tx, sc, c, ambiguous = _best_with_ambiguity(txns, feats, exp_type, exp_status)
        if best_tx is None or sc < AMOUNT:
            if best_tx is not None and sc >= TYPE and not ambiguous:
                # matched by type but no amount evidence -> still weak
                relevant, verdict = None, "insufficient_data"
                codes.append("weak_evidence")
                confidence = 0.6
            else:
                relevant, verdict = None, "insufficient_data"
                codes.append("needs_clarification" if txns else "no_transaction_history")
                confidence = 0.6 if not txns or sc == 0 else 0.6
        elif ambiguous:
            relevant, verdict = None, "insufficient_data"
            codes += ["ambiguous_match", "needs_clarification"]
            confidence = 0.65
        else:
            relevant, best_tx = best_tx.transaction_id, best_tx
            codes += c
            if case == "wrong_transfer" and established_recipient(best_tx, txns):
                verdict = "inconsistent"
                codes.append("established_recipient_pattern")
                codes.append("evidence_inconsistent")
                confidence = 0.75
            elif _status_contradicts(case, best_tx):
                # Data contradicts the complaint (e.g. claimed "failed" but status is
                # completed, or settlement already completed). Investigator must flag it.
                verdict = "inconsistent"
                codes.append("status_contradicts_claim")
                codes.append("evidence_inconsistent")
                confidence = 0.7
            else:
                verdict = "consistent"
                codes.append("transaction_match")
                if sc >= 12:
                    confidence = 0.92
                elif sc >= 10:
                    confidence = 0.9
                else:
                    confidence = 0.85

    severity = _severity(case, verdict, best_tx, base_sev)
    human_review = _human_review(case, verdict, relevant, best_tx)

    return {
        "case_type": case,
        "department": dept,
        "relevant_transaction_id": relevant,
        "evidence_verdict": verdict,
        "severity": severity,
        "human_review_required": human_review,
        "confidence": round(confidence, 2),
        "reason_codes": _dedup(codes),
        "_best_tx": best_tx,
        "_feats": feats,
    }


def _best(txns, feats, exp_type, exp_status):
    best, best_sc, best_codes = None, -1.0, []
    for tx in txns:
        sc, c = score_txn(tx, feats, exp_type, exp_status)
        if sc > best_sc:
            best, best_sc, best_codes = tx, sc, c
    return best, best_sc, best_codes


def _best_with_ambiguity(txns, feats, exp_type, exp_status):
    scored = []
    for tx in txns:
        sc, c = score_txn(tx, feats, exp_type, exp_status)
        scored.append((sc, tx, c))
    if not scored:
        return None, 0.0, [], False
    scored.sort(key=lambda x: x[0], reverse=True)
    top_sc = scored[0][0]
    # Ambiguous: 2+ transactions tie at top with amount-level evidence and different counterparties.
    tied = [s for s in scored if abs(s[0] - top_sc) < 0.01 and s[0] >= AMOUNT]
    distinct_cp = {s[1].counterparty for s in tied}
    ambiguous = len(tied) >= 2 and len(distinct_cp) >= 2
    return scored[0][1], top_sc, scored[0][2], ambiguous


def _severity(case, verdict, best_tx, base):
    sev = base
    if case == "wrong_transfer":
        sev = "high" if verdict == "consistent" else "medium"
    amt = best_tx.amount if best_tx else None
    if amt is not None and amt >= HIGH_VALUE and SEV_RANK[sev] < SEV_RANK["high"]:
        sev = "high"
    return sev


def _human_review(case, verdict, relevant, best_tx):
    if case in ("phishing_or_social_engineering", "duplicate_payment", "agent_cash_in_issue"):
        return True
    if case == "wrong_transfer":
        return relevant is not None
    if verdict == "inconsistent":
        return True
    if best_tx is not None and best_tx.amount is not None and best_tx.amount >= HIGH_VALUE:
        return True
    return False


def _dedup(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out
