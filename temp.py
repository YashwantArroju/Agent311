from _future_ import annotations
import os, json, base64
from typing import Optional, Dict, Any
from datetime import datetime
from email.mime.text import MIMEText

import boto3
from google.oauth2 import service_account
from googleapiclient.discovery import build

# ---------------- Config ----------------
GSA_SECRET_ID   = os.getenv("GSA_SECRET_ID", "gmail/service-account")
IMPERSONATE_USER = os.getenv("GMAIL_IMPERSONATE", "aiagent@lightningminds.com")
CITY_NAME        = os.getenv("CITY_NAME", "City")

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

_sm = boto3.client("secretsmanager")
_service = None


def _get_gmail_service():
    """Build a Gmail client using a service account with Domain-Wide Delegation."""
    global _service
    if _service is not None:
        return _service

    secret = _sm.get_secret_value(SecretId=GSA_SECRET_ID)["SecretString"]
    sa_info = json.loads(secret)

    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    delegated = creds.with_subject(IMPERSONATE_USER)
    _service = build("gmail", "v1", credentials=delegated, cache_discovery=False)
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
        description=description,
        ticket_id=ticket_id,
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


# ---------------- Lambda entrypoint ----------------
def handler(event, context) -> Dict[str, Any]:
    """
    Lambda entrypoint. Expects event like:

    {
      "to_email": "citizen@example.com",
      "ticket_id": "T-12345",
      "category": "Pothole",
      "description": "Large pothole near 5th & Main",
      "status": "Open",
      "city": "YourCity"
    }
    """
    try:
        # Parse event
        if isinstance(event, str):
            event = json.loads(event)

        to_email    = event["to_email"]
        ticket_id   = event["ticket_id"]
        category    = event.get("category")
        description = event.get("description")
        status      = event.get("status", "Open")
        city        = event.get("city")
        submitted_at = None

        if event.get("submitted_at"):
            submitted_at = datetime.fromisoformat(event["submitted_at"].replace("Z", "+00:00")).replace(tzinfo=None)

        return send_ticket_created_email(
            to_email=to_email,
            ticket_id=ticket_id,
            category=category,
            description=description,
            status=status,
            submitted_at=submitted_at,
            city=city,
        )
    except Exception as e:
        return {"ok": False, "error": str(e)}