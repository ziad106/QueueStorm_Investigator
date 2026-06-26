"""Deterministic outbound safety filter. Runs on every customer-facing string,
including LLM output, before it leaves the service. Never trusts upstream text."""
import re

WARN_EN = "Please do not share your PIN or OTP with anyone."

# A request that the customer hand over a secret credential.
CREDENTIAL_REQ = re.compile(
    r"(?:please\s+)?(?:share|send|provide|give|enter|tell us|confirm|type|submit|verify with)\b"
    r"[^.?!।]*\b(otp|pin|password|cvv|card\s*number|secret|credential)s?\b",
    re.I,
)
# Negation/warning context that makes a credential mention SAFE (telling user NOT to share).
NEG = re.compile(r"(do not|don't|dont|never|n't|without|do n't|avoid|refrain)", re.I)
NEG_BN = ("করবেন না", "চাই না", "দেবেন না", "জানাবেন না")
SAFE_RETURN = "any eligible amount will be returned through official channels"

# Unsafe promises of unauthorized action -> replace with safe wording.
PROMISES = [
    (re.compile(r"\bwe(?:\s*will|'ll|\s+are\s+going\s+to)\s+(?:refund|reverse|return|reimburse)\b[^.?!।]*", re.I), SAFE_RETURN),
    (re.compile(r"\byou(?:r)?\s+(?:money|amount|payment)\s+(?:will\s+be|has\s+been|is)\s+(?:refunded|reversed|returned)\b[^.?!।]*", re.I), SAFE_RETURN),
    (re.compile(r"\b(?:your\s+)?(?:refund|reversal)\s+(?:has\s+been|is\s+being|is)\s+(?:processed|approved|completed|done)\b[^.?!।]*", re.I), SAFE_RETURN),
    (re.compile(r"\byour\s+account\s+(?:will\s+be|has\s+been|is)\s+(?:unblocked|unlocked|restored|reactivated)\b[^.?!।]*", re.I), "our team will review your account status"),
    (re.compile(r"\bwe(?:\s*will|'ll)\s+(?:unblock|unlock|restore|reactivate)\b[^.?!।]*", re.I), "our team will review your account status"),
]

_SENT_SPLIT = re.compile(r"(?<=[.?!।])\s+")


def _is_credential_request(sentence):
    if not CREDENTIAL_REQ.search(sentence):
        return False
    if NEG.search(sentence) or any(b in sentence for b in NEG_BN):
        return False  # it's a "do not share..." warning, which is safe
    return True


def sanitize_reply(text):
    if not text:
        return WARN_EN
    kept = []
    for s in _SENT_SPLIT.split(text):
        if not s.strip():
            continue
        if _is_credential_request(s):
            continue  # drop unsafe credential-request sentence
        for pat, repl in PROMISES:
            s = pat.sub(repl, s)
        kept.append(s.strip())
    out = " ".join(kept)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([.?!,।])", r"\1", out)
    if not out or len(out) < 8:
        out = "We have noted your concern. Our team will review the case through official support channels. " + WARN_EN
    return out


def sanitize_action(text):
    """Recommended next action is agent-facing but must not promise unauthorized action."""
    if not text:
        return "Review the case and route to the appropriate team per policy."
    out = text
    for pat, repl in PROMISES:
        out = pat.sub(repl, out)
    return re.sub(r"\s{2,}", " ", out).strip()


def violates(text):
    """True only if text actually REQUESTS credentials (negated warnings are safe)."""
    for s in _SENT_SPLIT.split(text or ""):
        if _is_credential_request(s):
            return True
    return False
