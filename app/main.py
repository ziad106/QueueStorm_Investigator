"""QueueStorm Investigator API. GET /health + POST /analyze-ticket."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from .schemas import TicketIn
from .pipeline import analyze, safe_fallback

app = FastAPI(title="QueueStorm Investigator", version="1.0.0")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze-ticket")
async def analyze_ticket(request: Request):
    # 1. Parse JSON. Malformed body -> controlled 400, never a crash.
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "Invalid JSON body."})
    if not isinstance(body, dict):
        return JSONResponse(status_code=400, content={"error": "Request body must be a JSON object."})

    # 2. Validate against schema. Missing required fields -> 400.
    try:
        ticket = TicketIn(**body)
    except ValidationError:
        return JSONResponse(
            status_code=400,
            content={"error": "Missing or invalid required fields: 'ticket_id' and 'complaint' are required."},
        )

    # 3. Semantically empty complaint -> 422.
    if not ticket.complaint or not ticket.complaint.strip():
        return JSONResponse(
            status_code=422,
            content={"error": "Field 'complaint' must be a non-empty string."},
        )

    # 4. Analyze. Any unexpected error -> safe valid 200, never a 5xx.
    try:
        result = analyze(ticket)
    except Exception:
        result = safe_fallback(getattr(ticket, "ticket_id", None))
    return JSONResponse(status_code=200, content=result.model_dump())


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": "Internal error."})
