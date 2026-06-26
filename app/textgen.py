"""Deterministic, safe template text. agent_summary + recommended_next_action stay
English (agent-facing). customer_reply localizes to Bangla when complaint is Bangla."""
from . import extract as ex

WARN_EN = "Please do not share your PIN or OTP with anyone."
WARN_BN = "অনুগ্রহ করে কারো সাথে আপনার পিন বা ওটিপি শেয়ার করবেন না।"
OFFICIAL_EN = "through official support channels"
ELIGIBLE_EN = "any eligible amount will be returned through official channels"


def _amt(tx):
    if tx and tx.amount is not None:
        a = tx.amount
        return str(int(a)) if float(a).is_integer() else str(a)
    return "the reported"


def _tid(tx, dec):
    return tx.transaction_id if tx else (dec.get("relevant_transaction_id") or "the reported transaction")


def build_text(ticket, dec):
    tx = dec.get("_best_tx")
    case = dec["case_type"]
    verdict = dec["evidence_verdict"]
    tid = _tid(tx, dec)
    amt = _amt(tx)
    cp = tx.counterparty if tx and tx.counterparty else "the recipient"
    status = tx.status if tx and tx.status else "pending"
    lang = ex.reply_language(ticket.complaint or "", ticket.language)

    summary, action = _agent_text(case, verdict, tid, amt, cp, status)
    reply = _reply_bn(case, verdict, tid) if lang == "bn" else _reply_en(case, verdict, tid)
    return summary, action, reply


def _agent_text(case, verdict, tid, amt, cp, status):
    if case == "wrong_transfer" and verdict == "inconsistent":
        return (
            f"Customer claims {tid} ({amt} BDT to {cp}) was a wrong transfer, but transaction "
            f"history shows prior transfers to the same counterparty, suggesting an established recipient.",
            "Flag for human review. Verify with the customer whether this was genuinely a wrong "
            "transfer given the established transaction pattern with this recipient.",
        )
    if case == "wrong_transfer" and verdict == "insufficient_data":
        return (
            f"Customer reports a {amt} BDT transfer was not received, but multiple transactions of "
            "that amount exist and the correct one cannot be determined without more detail.",
            "Reply to the customer asking for the recipient's number to identify the correct "
            "transaction. Do not initiate a dispute until the transaction is confirmed.",
        )
    if case == "wrong_transfer":
        return (
            f"Customer reports sending {amt} BDT via {tid} to {cp}, which they now believe was the "
            "wrong recipient.",
            f"Verify {tid} details with the customer and initiate the wrong-transfer dispute workflow per policy.",
        )
    if case == "payment_failed":
        return (
            f"Customer attempted a {amt} BDT payment ({tid}) which failed but reports the balance was "
            "deducted. Requires payments operations investigation.",
            f"Investigate {tid} ledger status. If balance was deducted on a failed payment, initiate the "
            "automatic reversal flow within standard SLA.",
        )
    if case == "refund_request":
        return (
            f"Customer requests a refund of {amt} BDT for {tid} (merchant payment). Not a service failure.",
            "Inform the customer that refund eligibility depends on the merchant's own policy and guide "
            "them on contacting the merchant directly for a refund.",
        )
    if case == "duplicate_payment":
        return (
            f"Customer reports a duplicate payment. Two identical {amt} BDT payments to {cp} were completed "
            f"close together; {tid} is likely the duplicate.",
            f"Verify the duplicate with payments_ops. If the biller confirms only one payment was received, "
            f"initiate reversal of {tid}.",
        )
    if case == "merchant_settlement_delay":
        return (
            f"Merchant reports a {amt} BDT settlement ({tid}) is delayed beyond the expected window. "
            f"Settlement status is {status}.",
            "Route to merchant_operations to verify the settlement batch status and communicate a revised "
            "ETA if delayed.",
        )
    if case == "agent_cash_in_issue":
        return (
            f"Customer reports {amt} BDT cash-in via {cp} ({tid}) not reflected in balance. Transaction "
            f"status is {status}.",
            f"Investigate {tid} {status} status with agent operations. Confirm settlement state and resolve "
            "within the standard cash-in SLA.",
        )
    if case == "phishing_or_social_engineering":
        return (
            "Customer reports an unsolicited contact claiming to be from the company and requesting "
            "credentials. Likely a social engineering attempt.",
            "Escalate to the fraud_risk team immediately. Confirm to the customer that the company never "
            "asks for OTP or PIN, and log the reported contact for fraud pattern analysis.",
        )
    return (
        "Customer reports a vague concern without specifying a transaction, amount, or issue. Insufficient "
        "detail to identify a relevant transaction.",
        "Reply to the customer asking for specific details: which transaction, what amount, what went "
        "wrong, and the approximate time.",
    )


def _reply_en(case, verdict, tid):
    if case == "phishing_or_social_engineering":
        return (
            "Thank you for reaching out before sharing any information. We never ask for your PIN, OTP, or "
            "password under any circumstances. Please do not share these with anyone, even if they claim to "
            "be from us. Our fraud team has been notified of this incident."
        )
    if case == "refund_request":
        return (
            "Thank you for reaching out. Refunds for completed merchant payments depend on the merchant's own "
            "policy. We recommend contacting the merchant directly, and we can help you reach them if needed. "
            + WARN_EN
        )
    if case in ("payment_failed", "duplicate_payment"):
        noun = "a possible duplicate payment" if case == "duplicate_payment" else "an unexpected balance deduction"
        return (
            f"We have noted that transaction {tid} may have caused {noun}. Our payments team will review the "
            f"case and {ELIGIBLE_EN}. {WARN_EN}"
        )
    if case == "merchant_settlement_delay":
        return (
            f"We have noted your concern about settlement {tid}. Our merchant operations team will check the "
            f"batch status and update you on the expected settlement time {OFFICIAL_EN}."
        )
    if case == "agent_cash_in_issue":
        return (
            f"We have noted your concern about transaction {tid}. Our agent operations team will verify it "
            f"promptly and update you {OFFICIAL_EN}. {WARN_EN}"
        )
    if case == "wrong_transfer" and verdict == "insufficient_data":
        return (
            "Thank you for reaching out. We see multiple transactions of the same amount on that date. Could "
            f"you share the recipient's number so we can identify the right transaction? {WARN_EN}"
        )
    if case == "wrong_transfer":
        return (
            f"We have noted your concern about transaction {tid}. Our dispute team will review the case "
            f"carefully and contact you {OFFICIAL_EN}. {WARN_EN}"
        )
    # other / vague
    return (
        "Thank you for reaching out. To help you faster, please share the transaction ID, the amount "
        f"involved, and a short description of what went wrong. {WARN_EN}"
    )


def _reply_bn(case, verdict, tid):
    if case == "phishing_or_social_engineering":
        return (
            "কোনো তথ্য শেয়ার করার আগে যোগাযোগ করার জন্য ধন্যবাদ। আমরা কখনোই আপনার পিন, ওটিপি বা পাসওয়ার্ড "
            "চাই না। কেউ আমাদের পরিচয় দিলেও এসব কারো সাথে শেয়ার করবেন না। আমাদের ফ্রড টিমকে বিষয়টি জানানো হয়েছে।"
        )
    if case == "refund_request":
        return (
            "যোগাযোগ করার জন্য ধন্যবাদ। সম্পন্ন মার্চেন্ট পেমেন্টের রিফান্ড মার্চেন্টের নিজস্ব নীতির উপর নির্ভর "
            "করে। অনুগ্রহ করে সরাসরি মার্চেন্টের সাথে যোগাযোগ করুন; প্রয়োজনে আমরা সহায়তা করতে পারি। " + WARN_BN
        )
    if case in ("payment_failed", "duplicate_payment"):
        return (
            f"আপনার লেনদেন {tid} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের পেমেন্টস দল বিষয়টি যাচাই করবে এবং "
            f"যেকোনো প্রযোজ্য অর্থ অফিসিয়াল চ্যানেলের মাধ্যমে ফেরত দেওয়া হবে। {WARN_BN}"
        )
    if case == "merchant_settlement_delay":
        return (
            f"আপনার সেটেলমেন্ট {tid} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের মার্চেন্ট অপারেশন্স দল ব্যাচ স্ট্যাটাস "
            "যাচাই করে অফিসিয়াল চ্যানেলে আপনাকে জানাবে।"
        )
    if case == "agent_cash_in_issue":
        return (
            f"আপনার লেনদেন {tid} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের এজেন্ট অপারেশন্স দল এটি দ্রুত যাচাই করবে "
            f"এবং অফিসিয়াল চ্যানেলে আপনাকে জানাবে। {WARN_BN}"
        )
    if case == "wrong_transfer" and verdict == "insufficient_data":
        return (
            f"যোগাযোগ করার জন্য ধন্যবাদ। একই পরিমাণের একাধিক লেনদেন দেখা যাচ্ছে। সঠিক লেনদেনটি শনাক্ত করতে "
            f"অনুগ্রহ করে প্রাপকের নম্বরটি জানান। {WARN_BN}"
        )
    if case == "wrong_transfer":
        return (
            f"আপনার লেনদেন {tid} এর বিষয়ে আমরা অবগত হয়েছি। আমাদের ডিসপিউট দল বিষয়টি সতর্কতার সাথে যাচাই "
            f"করে অফিসিয়াল চ্যানেলে আপনার সাথে যোগাযোগ করবে। {WARN_BN}"
        )
    return (
        f"যোগাযোগ করার জন্য ধন্যবাদ। দ্রুত সহায়তার জন্য অনুগ্রহ করে লেনদেন আইডি, পরিমাণ এবং সমস্যার সংক্ষিপ্ত "
        f"বিবরণ জানান। {WARN_BN}"
    )
