# backend/db_core.py
import os, json, uuid
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, EmailStr

from sqlalchemy import (
    create_engine, event,
    Column, String, Integer, DateTime, Text, Float, ForeignKey
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session

# ---------------- Env / engine / session ----------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./backend/tickets.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()

# SQLite pragmas for smoother local concurrency
if DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def _sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")
        cur.execute("PRAGMA busy_timeout=3000;")
        cur.execute("PRAGMA foreign_keys=ON;")
        cur.close()

# ---------------- SQLAlchemy models ----------------
class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(String, primary_key=True, index=True)
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    address = Column(Text, nullable=False)
    lat = Column(Float, nullable=True)
    lon = Column(Float, nullable=True)
    dept = Column(String, nullable=True)
    status = Column(String, default="Open", nullable=False)
    eta_days = Column(Integer, default=5, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    # Backend-editable note shown when user checks status
    status_description = Column(Text, nullable=True)

    events = relationship("TicketEvent", back_populates="ticket", cascade="all, delete-orphan")

class TicketEvent(Base):
    __tablename__ = "ticket_events"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ticket_id = Column(String, ForeignKey("tickets.id", ondelete="CASCADE"), index=True, nullable=False)
    event_type = Column(String, nullable=False)   # e.g., "created", "status_changed", "comment"
    payload = Column(Text, nullable=True)         # JSON string
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    ticket = relationship("Ticket", back_populates="events")

# ---------------- Pydantic schemas ----------------
class CreateTicketRequest(BaseModel):
    category: str
    description: str
    address: str
    lat: Optional[float] = None
    lon: Optional[float] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None

class CreateTicketResponse(BaseModel):
    ticket_id: str
    status: str
    eta_days: int

class StatusRequest(BaseModel):
    ticket_id: str

# Allow optional note when updating status
class UpdateStatusRequest(BaseModel):
    ticket_id: str
    status: str
    status_description: Optional[str] = None

# ---------------- Helpers / CRUD ----------------
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

def init_db() -> None:
    # Creates tables if they don't exist (on a NEW DB this includes status_description).
    Base.metadata.create_all(bind=engine)

def create_ticket(
    db: Session,
    *,
    category: str,
    description: str,
    address: str,
    lat: float | None = None,
    lon: float | None = None,
    contact_email: str | None = None,
    contact_phone: str | None = None,
) -> Ticket:
    ticket_id = uuid.uuid4().hex[:8]
    t = Ticket(
        id=ticket_id,
        category=category,
        description=description,
        address=address,
        lat=lat, lon=lon,
        dept=route_department(category),
        status="Open",
        eta_days=5,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        contact_email=contact_email,
        contact_phone=contact_phone,
        # status_description intentionally left None at creation
    )
    db.add(t)
    db.commit()
    db.refresh(t)

    # event log (optional)
    ev = TicketEvent(ticket_id=t.id, event_type="created", payload=json.dumps({"category": category}))
    db.add(ev)
    db.commit()
    return t

def get_ticket(db: Session, ticket_id: str) -> Ticket | None:
    return db.query(Ticket).filter(Ticket.id == ticket_id).first()

def update_ticket_status(db: Session, ticket_id: str, status: str, status_description: str | None = None) -> Ticket | None:
    t = get_ticket(db, ticket_id)
    if not t:
        return None
    t.status = status
    if status_description is not None:
        t.status_description = status_description
    t.updated_at = datetime.utcnow()

    payload = {"status": status}
    if status_description is not None:
        payload["status_description"] = status_description

    db.add(TicketEvent(
        ticket_id=ticket_id,
        event_type="status_changed",
        payload=json.dumps(payload),
    ))
    db.commit()
    db.refresh(t)
    return t
