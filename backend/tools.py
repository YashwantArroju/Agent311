# backend/tools.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
# from typing import Optional, List, Dict   # ⬅️ no longer needed for DB-backed version
# from datetime import datetime             # ⬅️ no longer needed here
# import uuid                               # ⬅️ no longer needed here

app = FastAPI(title="311 Tools (DB-backed)")

# -------------------- OLD IN-MEMORY STORE (NOT USED) --------------------
# TICKETS: Dict[str, Dict] = {}  # ⬅️ replaced by SQLite in db_core.py

# class CreateTicketRequest(BaseModel):     # ⬅️ using canonical schemas from db_core.py
#     category: str
#     description: str
#     address: Optional[str] = None
#     lat: Optional[float] = None
#     lon: Optional[float] = None
#     contact_email: Optional[str] = None
#     contact_phone: Optional[str] = None
#     attachments: Optional[List[str]] = None
#
# class CreateTicketResponse(BaseModel):
#     ticket_id: str
#     status: str
#     eta_days: int
# -----------------------------------------------------------------------

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

# -------------------- Ticket endpoints --------------------
@app.post("/create_ticket", response_model=CreateTicketResponse)
def create_ticket(req: CreateTicketRequest):
    db = SessionLocal()
    try:
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
        return CreateTicketResponse(ticket_id=t.id, status=t.status, eta_days=t.eta_days)
    finally:
        db.close()

@app.post("/get_ticket_status")
def get_ticket_status(req: StatusRequest):
    db = SessionLocal()
    try:
        t = db_get_ticket(db, req.ticket_id)
        if not t:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {
            "ticket_id": t.id,
            "status": t.status,
            "dept": t.dept,
            "created_at": t.created_at.isoformat(),
            "eta_days": t.eta_days,
            # convenience extras
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
        t = db_update_ticket_status(db, req.ticket_id, req.status)
        if not t:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return {"ok": True, "ticket_id": t.id, "status": t.status}
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
            "For a streetlight outage, include the nearest address/intersection (and pole number if visible). "
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

# -------------------- OLD ROUTER (NOT USED HERE) --------------------
# def route_department(category: str) -> str:   # ⬅️ handled inside db_core.create_ticket
#     mapping = {
#         "pothole": "Public Works",
#         "streetlight": "Transportation",
#         "missed_trash": "Sanitation",
#         "graffiti": "Public Works",
#         "noise": "Code Enforcement",
#         "bulk_pickup": "Sanitation",
#     }
#     return mapping.get((category or "").lower(), "311 Intake")
