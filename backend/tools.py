# backend/tools.py
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import datetime
import uuid

app = FastAPI(title="311 Tools (Generic)")

# In-memory ticket store (non-persistent; fine for MVP)
TICKETS: Dict[str, Dict] = {}


class CreateTicketRequest(BaseModel):
    category: str
    description: str
    address: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    attachments: Optional[List[str]] = None


class CreateTicketResponse(BaseModel):
    ticket_id: str
    status: str
    eta_days: int


@app.post("/create_ticket", response_model=CreateTicketResponse)
def create_ticket(req: CreateTicketRequest):
    ticket_id = uuid.uuid4().hex[:8]
    TICKETS[ticket_id] = {
        "id": ticket_id,
        "category": req.category,
        "description": req.description,
        "address": req.address,
        "lat": req.lat,
        "lon": req.lon,
        "created_at": datetime.utcnow().isoformat(),
        "status": "Open",
        "eta_days": 5,
        "dept": route_department(req.category),
        "contact_email": req.contact_email,
        "contact_phone": req.contact_phone,
        "attachments": req.attachments or [],
    }
    return CreateTicketResponse(ticket_id=ticket_id, status="Open", eta_days=5)


class StatusRequest(BaseModel):
    ticket_id: str


@app.post("/get_ticket_status")
def get_ticket_status(req: StatusRequest):
    t = TICKETS.get(req.ticket_id)
    if not t:
        return {"error": "Ticket not found"}
    return {
        "ticket_id": t["id"],
        "status": t["status"],
        "dept": t["dept"],
        "created_at": t["created_at"],
        "eta_days": t["eta_days"],
    }


class KBQuery(BaseModel):
    query: str


# Simple, city-agnostic FAQ snippets
_FAQ = [
    {"q": "missed trash", "a": "If your trash was missed, leave bins curbside and report the address; most cities recollect next business day."},
    {"q": "pothole", "a": "Report potholes with the nearest address or intersection; typical repair time is 3–7 days."},
    {"q": "streetlight", "a": "Provide the nearest address/intersection and, if possible, the pole number for a streetlight outage."},
    {"q": "noise", "a": "Most cities have quiet hours around 10PM–7AM. Share address and times to file a noise complaint."},
    {"q": "bulk pickup", "a": "Large items (sofa/mattress) often require scheduled bulk pickup. Share item type and address to request it."},
]


@app.post("/search_kb")
def search_kb(req: KBQuery):
    q = (req.query or "").lower()
    for item in _FAQ:
        if item["q"] in q:
            return {"answer": item["a"], "source": "Generic FAQs"}
    return {"answer": None, "source": None}


def route_department(category: str) -> str:
    mapping = {
        "pothole": "Public Works",
        "streetlight": "Transportation",
        "missed_trash": "Sanitation",
        "graffiti": "Public Works",
        "noise": "Code Enforcement",
        "bulk_pickup": "Sanitation",
    }
    return mapping.get((category or "").lower(), "311 Intake")
