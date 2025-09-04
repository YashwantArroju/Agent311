# backend/email.py
from __future__ import annotations
import os
import base64
from typing import Optional
from datetime import datetime
from email.mime.text import MIMEText

from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------- Config ----------------
SA_JSON_PATH = os.getenv("GMAIL_SA_FILE", "backend/credentials/service_account.json")
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
IMPERSONATE_USER = os.getenv("GMAIL_IMPERSONATE", "aiagent@lightningminds.com")
CITY_NAME = os.getenv("CITY_NAME", "City")

_service = None

def _get_gmail_service():
    """Build a Gmail client using a service account with Domain-Wide Delegation."""
    global _service
    if _service is not None:
        return _service

    if not os.path.exists(SA_JSON_PATH):
        raise FileNotFoundError(f"Service account JSON not found at: {SA_JSON_PATH}")

    creds = service_account.Credentials.from_service_account_file(
        SA_JSON_PATH, scopes=SCOPES
    )
    delegated = creds.with_subject(IMPERSONATE_USER)  # impersonate mailbox
    _service = build("gmail", "v1", credentials=delegated)
    return _service

def compose_city311_plaintext(
    *,
    city: str,
    category: Optional[str],
    description: Optional[str],   
    ticket_id: int | str,
    status: str,
    submitted_at: Optional[datetime] = None,
) -> str:
    """
    Build the plain-text confirmation body. No timezone conversion—uses submitted_at as provided.
    If submitted_at is None, falls back to current UTC time (naive).
    """
    dt = submitted_at or datetime.utcnow()
    date_str = f"{dt.month}/{dt.day}/{dt.year}"

    return (
        "Hello,\n"
        "\n"
        f"Thank you for contacting {city} 311. We strive to process requests within one to two business days. "
        "If your request is more urgent, please call 311, and always call 911 when there is an immediate threat to life or property.\n"
        " \n"
        f"We appreciate your support in keeping {city} one of the best places to live, work and raise a family. "
        "Please add this email to your approved sender list to continue to receive updates regarding the case.\n"
        " \n"
        "Case Details\n"
        f"Category: {category or '-'}\n"
        f"Ticket: {ticket_id}\n"
        f"Description: {description or '-'}\n"
        f"Status: {status}\n"
        "\n"
        f"Date Submitted: {date_str}\n"
        " \n"
        "Thank You,\n"
        f"Your {city} 311 Team\n"
    )

def send_email_sa(
    *,
    subject: str,
    text_body: str,
    recipient: str,
    reply_to: Optional[str] = None,
) -> dict:
    """Send a plain-text email via Gmail API using service account impersonation."""
    service = _get_gmail_service()

    msg = MIMEText(text_body, _subtype="plain", _charset="utf-8")
    msg["to"] = recipient
    msg["subject"] = subject
    from_header = f"{CITY_NAME} 311 Team <{IMPERSONATE_USER}>"
    msg["from"] = from_header
    if reply_to:
        msg["Reply-To"] = reply_to

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    res = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return {
        "messageId": res.get("id"),
        "to": recipient,
        "from": from_header,
        "subject": subject,
    }

def send_ticket_created_email(
    *,
    to_email: str,
    ticket_id: int | str,
    category: Optional[str],
    description: Optional[str] = None,
    status: str = "Open",
    submitted_at: Optional[datetime] = None,
    city: Optional[str] = None,
) -> dict:
    """Compose + send the generalized City 311 ticket confirmation (plain text)."""
    city_name = city or CITY_NAME
    body = compose_city311_plaintext(
        city=city_name,
        category=category,
        ticket_id=ticket_id,
        description=description, 
        status=status,
        submitted_at=submitted_at,
    )
    subject = f"{city_name} 311 – Case Received (Ticket #{ticket_id})"
    return send_email_sa(
        subject=subject,
        text_body=body,
        recipient=to_email,
        reply_to=IMPERSONATE_USER,
    )
