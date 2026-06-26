"""Deterministic feature extraction from complaint text. No external calls."""
import re
from datetime import datetime, timedelta

BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

# Multilingual keyword banks (en / bn / banglish). Complaint is untrusted DATA only.
KW = {
    "phishing": [
        "otp", "pin", "password", "cvv", "card number", "scam", "phishing", "fraud",
        "suspicious", "click", "link", "verify your account", "account will be blocked",
        "asked for my", "asked me for", "claiming to be", "claim to be", "they are from",
        "ওটিপি", "পিন", "পাসওয়ার্ড", "প্রতারক", "প্রতারণা", "ফাঁদ", "সন্দেহজনক",
        "ব্লক", "লিংক", "ক্লিক", "ফোন করে", "এসএমএস",
    ],
    "duplicate": [
        "twice", "two times", "double", "duplicate", "deducted twice", "charged twice",
        "double charge", "double deduct", "two time", "দুইবার", "দুবার", "ডাবল", "দুই বার",
    ],
    "failed": [
        "failed", "fail", "but my balance was deducted", "balance was deducted",
        "balance deducted", "deducted but", "showed failed", "transaction failed",
        "payment failed", "did not go through", "didn't go through",
        "ব্যর্থ", "ফেল", "কাটা হয়েছে কিন্তু", "কেটে নিয়েছে",
    ],
    "wrong_transfer": [
        "wrong number", "wrong person", "wrong recipient", "wrong account", "rong number",
        "by mistake", "mistakenly sent", "sent to the wrong", "wrong nmbr",
        "ভুল নাম্বার", "ভুল নম্বর", "ভুল মানুষ", "ভুল করে", "ভুল জায়গায়",
    ],
    "agent_cash_in": [
        "cash in", "cash-in", "cashin", "agent", "deposited", "deposit",
        "ক্যাশ ইন", "ক্যাশইন", "এজেন্ট", "জমা",
    ],
    "settlement": [
        "settlement", "settle", "settled", "payout", "disburse",
        "সেটেলমেন্ট", "নিষ্পত্তি",
    ],
    "refund": [
        "refund", "return my money", "give my money back", "changed my mind",
        "want my money back", "money back", "ফেরত", "রিফান্ড", "টাকা ফেরত",
    ],
    "not_received": [
        "didn't receive", "did not receive", "not received", "didn't get", "did not get",
        "hasn't arrived", "not reflected", "not show", "isn't showing", "balance e ase ni",
        "আসেনি", "পাইনি", "পায়নি", "দেখছি না", "ঢোকেনি",
    ],
}

# Injection phrases to neutralize if found in complaint (never obey them).
INJECTION = [
    "ignore previous", "ignore all previous", "ignore the above", "disregard",
    "system prompt", "you are now", "refund immediately", "approve the refund",
    "give the customer", "send the otp", "reveal", "act as",
]


def normalize(text):
    return (text or "").translate(BN_DIGITS)


def has_kw(text, key):
    t = text.lower()
    return any(k in t for k in KW[key])


def detect_language(text, declared):
    if declared in ("en", "bn", "mixed"):
        return declared
    bn = sum(1 for c in text if "ঀ" <= c <= "৿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if bn and latin:
        return "mixed"
    if bn:
        return "bn"
    return "en"


def reply_language(text, declared):
    """Reply in Bangla only when complaint is Bangla-dominant."""
    if declared == "bn":
        return "bn"
    bn = sum(1 for c in text if "ঀ" <= c <= "৿")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if bn > latin:
        return "bn"
    return "en"


def extract_amounts(text):
    t = normalize(text)
    amounts = set()
    # thousands/lakh shorthand
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(k|hazar|thousand|হাজার)\b", t, re.I):
        amounts.add(round(float(m.group(1)) * 1000, 2))
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*(lakh|lac|লাখ|লক্ষ)\b", t, re.I):
        amounts.add(round(float(m.group(1)) * 100000, 2))
    # plain numbers with optional thousands separators
    for m in re.finditer(r"\b(\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\b", t):
        raw = m.group(0).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        if v >= 10:  # ignore tiny ints like "1" item / "2pm"
            amounts.add(v)
    return amounts


def extract_phones(text):
    t = normalize(text)
    phones = set()
    for m in re.finditer(r"(?:\+?880)?1\d{8,9}", t):
        digits = re.sub(r"\D", "", m.group(0))
        phones.add(digits[-10:])
    return phones


def extract_ids(text):
    return set(re.findall(r"\b(?:TXN|AGENT|MERCHANT|BILLER)[-\w]+\b", text, re.I))


def parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def extract_time_hint(text):
    """Return (day_offset, hour) hints. day_offset: 0 today, -1 yesterday, None unknown."""
    t = normalize(text).lower()
    day = None
    if any(w in t for w in ("yesterday", "গতকাল", "kal", "gotokal")):
        day = -1
    elif any(w in t for w in ("today", "আজ", "aj", "ajke", "আজকে")):
        day = 0
    hour = None
    m = re.search(r"(\d{1,2})\s*(am|pm)", t)
    if m:
        hour = int(m.group(1)) % 12 + (12 if m.group(2) == "pm" else 0)
    elif any(w in t for w in ("morning", "সকাল", "shokal")):
        hour = 9
    elif "noon" in t or "দুপুর" in t or "dupur" in t:
        hour = 13
    elif any(w in t for w in ("evening", "বিকাল", "bikal", "সন্ধ্যা")):
        hour = 18
    elif any(w in t for w in ("night", "রাত", "rat")):
        hour = 21
    return day, hour


def has_injection(text):
    t = (text or "").lower()
    return any(p in t for p in INJECTION)


def extract_features(complaint, declared_lang, txns):
    ref = None
    for tx in txns:
        d = parse_ts(tx.timestamp)
        if d and (ref is None or d > ref):
            ref = d
    return {
        "amounts": extract_amounts(complaint),
        "phones": extract_phones(complaint),
        "ids": extract_ids(complaint),
        "day_offset": extract_time_hint(complaint)[0],
        "hour": extract_time_hint(complaint)[1],
        "language": detect_language(complaint, declared_lang),
        "ref_today": ref,
        "injection": has_injection(complaint),
    }
