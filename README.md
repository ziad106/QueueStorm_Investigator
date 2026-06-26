# QueueStorm Investigator

Internal support-agent copilot for a digital-finance platform. It receives one support
ticket plus recent transaction history and returns a structured JSON decision that
classifies, routes, explains, and safely replies to the customer.

Built for the SUST CSE Carnival 2026 — Codex Community Hackathon (Online Preliminary).
The service is a **support copilot, not an autonomous financial authority**: it never asks
for credentials, never promises unauthorized actions, and escalates risky/ambiguous cases.

## Tech Stack
- **Backend:** Python 3.11 + FastAPI + Uvicorn
- **Validation:** Pydantic v2 (strict output schema, permissive input)
- **Reasoning:** Deterministic rule-based investigation engine (no model required)
- **AI (optional):** Google Gemini, text-polish only, disabled by default
- **Deployment:** Any host; Docker fallback included (image < 200 MB, no GPU)

## Endpoints
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness. Returns `{"status":"ok"}`. |
| POST | `/analyze-ticket` | Analyze one ticket, return structured JSON. |

### Status codes
`200` valid analysis · `400` malformed JSON / missing required field ·
`422` valid shape but empty `complaint` · `500` only for truly unexpected internal error
(the analysis path additionally falls back to a safe `200`, so 5xx is effectively never hit).

## Setup
```bash
git clone <repo>
cd <repo>
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Run with Docker
```bash
docker build -t queuestorm-team .
docker run -p 8000:8000 --env-file judging.env queuestorm-team   # env-file optional
```

## Environment Variables
All optional — the service runs fully in deterministic mode with none set. See `.env.example`.
- `PORT` (default 8000)
- `LLM_PROVIDER=gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `LLM_TIMEOUT` — enable the optional
  text-polish layer. If unset, slow, rate-limited, or failing, the deterministic templates are used.

## Sample Request
```json
{
  "ticket_id": "TKT-001",
  "complaint": "I sent 5000 taka to a wrong number around 2pm today.",
  "language": "en",
  "channel": "in_app_chat",
  "user_type": "customer",
  "transaction_history": [
    {"transaction_id":"TXN-9101","timestamp":"2026-04-14T14:08:22Z","type":"transfer",
     "amount":5000,"counterparty":"+8801719876543","status":"completed"}
  ]
}
```

## Sample Response
```json
{
  "ticket_id": "TKT-001",
  "relevant_transaction_id": "TXN-9101",
  "evidence_verdict": "consistent",
  "case_type": "wrong_transfer",
  "severity": "high",
  "department": "dispute_resolution",
  "agent_summary": "Customer reports sending 5000 BDT via TXN-9101 to +8801719876543, which they now believe was the wrong recipient.",
  "recommended_next_action": "Verify TXN-9101 details with the customer and initiate the wrong-transfer dispute workflow per policy.",
  "customer_reply": "We have noted your concern about transaction TXN-9101. Our dispute team will review the case carefully and contact you through official support channels. Please do not share your PIN or OTP with anyone.",
  "human_review_required": true,
  "confidence": 0.92,
  "reason_codes": ["wrong_transfer","amount_match","type_match","timestamp_match","status_completed","transaction_match"]
}
```
Generated outputs for all 10 public sample cases are in [`sample_output.json`](sample_output.json).

## Architecture
```
Request
  -> input validation (Pydantic, permissive)         app/schemas.py
  -> feature extraction (amount/phone/time/lang/kw)   app/extract.py
  -> deterministic investigation engine               app/engine.py
       relevant_transaction_id, evidence_verdict, case_type,
       department, severity, human_review_required, confidence
  -> template text (agent_summary / next_action / reply, en+bn)  app/textgen.py
  -> OPTIONAL Gemini polish of the 3 text fields only  app/llm.py
  -> deterministic safety filter (always last word)    app/safety.py
  -> strict output schema validation                   app/schemas.py
  -> JSON 200
```
Decision fields are **always** deterministic. The LLM can only reword the three free-text
fields and can never alter a decision; its output still passes through the safety filter.

## Evidence Reasoning
- **Transaction matching:** every transaction is scored against the complaint — amount (+5),
  type (+4), counterparty mention (+3), time/date hint (+3), status (+2). Highest score wins.
- **Ambiguity guard:** if 2+ transactions tie at the top with amount-level evidence and
  different counterparties, we return `relevant_transaction_id=null` +
  `evidence_verdict=insufficient_data` and ask for a disambiguator. We never guess.
- **Verdict:** `consistent` (evidence supports), `inconsistent` (e.g. a "wrong transfer" to an
  established repeat recipient), `insufficient_data` (no/ambiguous/empty evidence).
- **Duplicate detection:** two near-identical payments (same amount/counterparty/type within
  an hour) → `duplicate_payment`, relevant id = the later (duplicate) one.
- **Routing/severity/review** derive from case type + evidence (see `engine.py`).
- **Amount/time normalization:** `5k`, `5,000`, Bangla digits (৫০০০), and `today/yesterday/
  2pm/morning` are normalized before matching.

## Safety Logic
Deterministic guardrails, independent of any model:
- **Never requests credentials.** Any sentence asking the customer to share PIN/OTP/password/
  CVV/card number is stripped from the reply (negated *warnings* like "do not share your OTP"
  are preserved).
- **No unauthorized promises.** "We will refund/reverse/unblock…" is rewritten to "any eligible
  amount will be returned through official channels" / "our team will review your account status".
- **Official channels only.** Replies route customers to official support, never third parties.
- **Prompt-injection defense.** The complaint is treated strictly as data; instructions embedded
  in it ("ignore previous…", "approve refund", "ask for OTP") never affect control flow or output.
- **Phishing reports** → `fraud_risk`, `critical`, human review, and a reply reinforcing that we
  never ask for credentials.

## AI / MODELS
| Component | Where it runs | Why | Failure handling |
|---|---|---|---|
| Rule-based investigation engine | In-process (CPU) | Deterministic, fast (p95 ≈ 1 ms), no key, fully reproducible. Owns all scored fields. | N/A — primary path |
| Google Gemini `gemini-2.5-flash` (optional) | External API (team key) | Polish of the 3 free-text fields for Response Quality. Run with `thinkingBudget=0` for ~2 s latency. | Timeout/error/quota(429)/invalid JSON → deterministic templates; output still safety-filtered |

The system is **fully functional and scores Stage-1 (evidence, safety, schema, performance)
without any LLM or API key.** The LLM is a strictly-bounded enhancement: it only rewords the
three text fields, never a decision, and every reply still passes the deterministic safety
filter. Disable it any time by unsetting `LLM_PROVIDER` (pure deterministic, p95 ≈ 1 ms).

## Performance
- `/health` ready in < 1 s of start.
- Deterministic `/analyze-ticket`: p95 ≈ 1–6 ms locally, well under the 5 s full-credit bar.
- Stable on malformed JSON, empty/large transaction history, unknown enum values, and
  multilingual input (no crashes; controlled responses).

## Tests
```bash
python tests/run_samples.py   # 10 public cases: decision fields + reply safety
python tests/run_edge.py      # injection, phishing, empty/large history, Bangla, filters
```

## Known Limitations
- Time matching uses the most recent transaction as the "today" reference (no real clock in
  request), so relative-time hints are approximate.
- Amount parsing covers digits, `k`/`thousand`/`lakh` and Bangla digits, not full free-form
  word numbers ("five thousand" is partially handled).
- Free-text replies are template-based unless the optional LLM is enabled; they are safe and
  professional but less varied than model-generated text.
- Heuristic keyword classification may need extension for unusual phrasings; ambiguous cases
  deliberately fall back to `insufficient_data` + human review rather than guessing.

## No Secrets / No Real Data
No real customer data is used (all synthetic). No secrets are committed; `.env.example`
contains variable names only. Real keys, if the optional LLM is used, are provided via the
hosting platform's environment, never the repository.

## Credits
FastAPI, Uvicorn, Pydantic (open-source). Optional: Google Gemini API.
