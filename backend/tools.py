# backend/tools.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, BackgroundTasks
from .email import send_ticket_created_email
import traceback
import json 
from .db_core import TicketEvent




app = FastAPI(title="311 Tools (DB-backed)")

#helper to find email success/failure
def _send_email_background(*, to_email: str, ticket_id: str, category: str,
                           description: str, status: str, created_at: datetime,
                           from_user: str | None = None):
    try:
        # local import to avoid reload races
        from .email import send_ticket_created_email
        res = send_ticket_created_email(
            to_email=to_email,
            ticket_id=ticket_id,
            category=category,
            description=description,
            status=status,
            submitted_at=created_at,
        )
        print(f"[EMAIL OK] ticket={ticket_id} to={res.get('to')} from={res.get('from')} msgId={res.get('messageId')}")
    except Exception as e:
        print(f"[EMAIL ERR] ticket={ticket_id}: {e}")
        traceback.print_exc()

# -------------------- DB IMPORTS (single-file core) --------------------
from .db_core import (
    # engine/Session + init
    SessionLocal, init_db,
    # canonical request/response schemas
    CreateTicketRequest, CreateTicketResponse, StatusRequest, UpdateStatusRequest,
    # CRUD helpers
    create_ticket as db_create_ticket,
    get_ticket as db_get_ticket,
    update_ticket_status as db_update_ticket_status,
)

# Create tables on import (simple for dev)
init_db()

# -------------------- Response models --------------------
class StatusResponse(BaseModel):
    ticket_id: str
    status: str
    status_description: Optional[str] = None
    eta_days: int
    dept: Optional[str] = None
    updated_at: datetime

class SendConfirmationRequest(BaseModel):
    ticket_id: str

# -------------------- Ticket endpoints --------------------
@app.post("/create_ticket", response_model=CreateTicketResponse)
def create_ticket(req: CreateTicketRequest, background: BackgroundTasks):
    db = SessionLocal()
    try:
         # (redundant once schema required, but nice error if someone bypasses)
        if not req.contact_email:
            raise HTTPException(status_code=400, detail="contact_email is required")
        
        t = db_create_ticket(
            db,
            category=req.category,
            description=req.description,
            address=req.address,
            lat=req.lat,
            lon=req.lon,
            contact_email=req.contact_email,
            contact_phone=req.contact_phone,
        )
         # Auto-send confirmation ONLY if we have a contact_email
        '''if t.contact_email:
            background.add_task(
                send_ticket_created_email,
                to_email=t.contact_email,
                ticket_id=t.id,
                category=t.category,
                description=t.description,
                status=t.status,      # your DB default is "Open"
                submitted_at=t.created_at,      # <-- Date Submitted from DB
                # city=None  # omit to use CITY_NAME env
            )
        # Always enqueue (email is guaranteed by schema)
        background.add_task(
            _send_email_background,
            to_email=t.contact_email,
            ticket_id=t.id,
            category=t.category,
            description=t.description,
            status=t.status,
            created_at=t.created_at,
            #from_user="AiAgent@lightningminds.com",  # uncomment to lock sender
        )'''

        return CreateTicketResponse(ticket_id=t.id, status=t.status, eta_days=t.eta_days)
    finally:
        db.close()

@app.post("/get_ticket_status", response_model=StatusResponse, response_model_exclude_none=True)
def get_ticket_status(req: StatusRequest):
    db = SessionLocal()
    try:
        t = db_get_ticket(db, req.ticket_id)
        if not t:
            raise HTTPException(status_code=404, detail="Ticket not found")
        
         # --- compute ETA remaining based on creation date (calendar days) ---
        days_elapsed = max(0, (datetime.utcnow().date() - t.created_at.date()).days)
        eta_remaining = max(0, (t.eta_days or 0) - days_elapsed)
        # Only the fields in StatusResponse will be returned (others are ignored by response_model)
        return {
            "ticket_id": t.id,
            "status": t.status,
            "status_description": t.status_description,  # <- note surfaces here
            "eta_days": eta_remaining,      # <= dynamic ETA shown here
            "dept": t.dept,
            "updated_at": t.updated_at,
            # extras (kept here for convenience; filtered out by response_model)
            "created_at": t.created_at.isoformat(),
            "category": t.category,
            "address": t.address,
            "description": t.description,
            "contact_email": t.contact_email,
        }
    finally:
        db.close()

@app.post("/update_ticket_status")
def update_ticket_status(req: UpdateStatusRequest):
    db = SessionLocal()
    try:
        # Forward optional status_description to DB layer
        t = db_update_ticket_status(db, req.ticket_id, req.status, req.status_description)
        if not t:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {
            "ok": True,
            "ticket_id": t.id,
            "status": t.status,
            "status_description": t.status_description,
        }
    finally:
        db.close()

@app.post("/send_confirmation")
def send_confirmation(req: SendConfirmationRequest):
    db = SessionLocal()
    try:
        t = db_get_ticket(db, req.ticket_id)
        if not t:
            raise HTTPException(status_code=404, detail="Ticket not found")
        if not t.contact_email:
            raise HTTPException(status_code=400, detail="Ticket has no contact_email")

        # Idempotency: has a confirmation already been sent?
        already = any(ev.event_type == "email_sent" for ev in t.events)
        if already:
            return {"ok": True, "already_sent": True, "ticket_id": t.id}

        # Send now (synchronously so the tool gets immediate success/failure)
        from .email import send_ticket_created_email
        res = send_ticket_created_email(
            to_email=t.contact_email,
            ticket_id=t.id,
            category=t.category,
            description=t.description,
            status=(t.status or "Open"),
            submitted_at=t.created_at,
        )

        # Record the send
        db.add(TicketEvent(
            ticket_id=t.id,
            event_type="email_sent",
            payload=json.dumps({"messageId": res.get("messageId")})
        ))
        db.commit()

        return {
            "ok": True,
            "already_sent": False,
            "ticket_id": t.id,
            "to": res.get("to"),
            "from": res.get("from"),
            "messageId": res.get("messageId"),
        }
    except HTTPException:
        raise
    except Exception as e:
        # Surface any Gmail/API error to the caller
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"email_send_failed: {e}")
    finally:
        db.close()

# -------------------- Knowledge base (FAQs) --------------------
class KBQuery(BaseModel):
    query: str

# Generalized, action-forward answers (not city-specific)
_FAQ = [
    {
        "q": "missed trash",
        "a": (
            "For missed trash, keep bins curbside; re-collection is often the next business day. "
            "If you’d like, I can create a service ticket to alert the sanitation team."
        ),
    },
    {
        "q": "pothole",
        "a": (
            "Potholes are typically handled by public works. Repairs often take a few days once logged. "
            "Want me to create a ticket with the location and a short description?"
        ),
    },
    {
        "q": "streetlight",
        "a": (
            "For a streetlight outage, it generally takes 3-5 business days to fix. "
            "I can create a ticket for you now."
        ),
    },
    {
        "q": "noise",
        "a": (
            "Most places have quiet hours (often ~10PM–7AM). Non-emergency noise concerns can be logged for follow-up. "
            "Shall I create a ticket to document the times and location?"
        ),
    },
    {
        "q": "bulk pickup",
        "a": (
            "Bulk items (e.g., sofa, mattress) usually need scheduled pickup. "
            "If you’d like, I can create a ticket to start the request."
        ),
    },
]

@app.post("/search_kb")
def search_kb(req: KBQuery):
    q = (req.query or "").lower()
    for item in _FAQ:
        if item["q"] in q:
            return {"answer": item["a"], "source": "Generic FAQs"}
    return {"answer": None, "source": None}
