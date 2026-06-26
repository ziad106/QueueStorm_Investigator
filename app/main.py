"""QueueStorm Investigator API. GET /health + POST /analyze-ticket."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from .schemas import TicketIn
from .pipeline import analyze, safe_fallback

app = FastAPI(title="QueueStorm Investigator", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.exception_handler(RequestValidationError)
async def on_validation_error(request: Request, exc: RequestValidationError):
    # Malformed JSON or missing/invalid required fields -> controlled 400 (spec 4.1),
    # never FastAPI's default 422 and never a crash.
    return JSONResponse(
        status_code=400,
        content={"error": "Malformed input: 'ticket_id' and 'complaint' are required, body must be valid JSON."},
    )


@app.post("/analyze-ticket")
async def analyze_ticket(ticket: TicketIn):
    # Schema valid but semantically empty complaint -> 422 (spec 4.1).
    if not ticket.complaint or not ticket.complaint.strip():
        return JSONResponse(status_code=422, content={"error": "Field 'complaint' must be a non-empty string."})

    # Analyze in a threadpool so the blocking LLM call never stalls the event loop
    # (a single hung request must not freeze concurrent /health or other requests).
    # Any unexpected error -> safe valid 200, never a 5xx.
    try:
        result = await run_in_threadpool(analyze, ticket)
    except Exception:
        result = safe_fallback(ticket.ticket_id)
    return JSONResponse(status_code=200, content=result.model_dump())


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal error."})
