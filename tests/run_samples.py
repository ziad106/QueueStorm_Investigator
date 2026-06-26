"""Validate the engine against the 10 public sample cases + safety/edge checks.
Decision fields must match expected; free text only checked for safety."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.schemas import TicketIn  # noqa: E402
from app.pipeline import analyze  # noqa: E402
from app import safety  # noqa: E402

DECISION = ["relevant_transaction_id", "evidence_verdict", "case_type", "department",
            "severity", "human_review_required"]
UNSAFE_REQ = ["share your otp", "send your otp", "provide your pin", "give us your pin",
              "your password", "we will refund", "you will be refunded",
              "account will be unblocked", "refund has been processed"]


def safe_reply(reply):
    low = reply.lower()
    if safety.violates(reply):
        return False, "credential request"
    for p in UNSAFE_REQ:
        if p in low:
            return False, f"unsafe phrase: {p}"
    return True, ""


def main():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data = json.load(open(os.path.join(here, "SUST_Preli_Sample_Cases.json")))
    passed = failed = 0
    for case in data["cases"]:
        tin = TicketIn(**case["input"])
        out = analyze(tin).model_dump()
        exp = case["expected_output"]
        diffs = [f for f in DECISION if out[f] != exp[f]]
        ok_reply, why = safe_reply(out["customer_reply"])
        if diffs or not ok_reply:
            failed += 1
            print(f"FAIL {case['id']}")
            for f in diffs:
                print(f"   {f}: got {out[f]!r} expected {exp[f]!r}")
            if not ok_reply:
                print(f"   SAFETY: {why}")
        else:
            passed += 1
            print(f"PASS {case['id']}  ({out['case_type']}/{out['evidence_verdict']}/"
                  f"sev={out['severity']}/review={out['human_review_required']})")
    print(f"\n{passed}/{passed + failed} decision-matched")
    return failed


if __name__ == "__main__":
    sys.exit(1 if main() else 0)
