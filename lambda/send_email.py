# email.py
from __future__ import annotations
from datetime import datetime
from email.mime.text import MIMEText
from typing import Optional
import base64
import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build

import boto3
from botocore.exceptions import ClientError

# ---------------- Config ----------------
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
IMPERSONATE_USER = os.getenv("GMAIL_IMPERSONATE", "aiagent@lightningminds.com")
CITY_NAME = os.getenv("CITY_NAME", "Cityville")

_service = None


def get_secret():

    secret_name = "app/311/gmail/service_account.json"
    region_name = "us-east-1"

    # Create a Secrets Manager client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        # For a list of exceptions thrown, see
        # https://docs.aws.amazon.com/secretsmanager/latest/apireference/API_GetSecretValue.html
        raise e

    return get_secret_value_response['SecretString']

def _get_gmail_service(secret: str):
    """Build a Gmail client using a service account with Domain-Wide Delegation."""
    global _service
    if _service is not None:
        return _service
    
    # Parse and convert secret string to json
    try:
        service_account_info = json.loads(secret)
    except json.JSONDecodeError:
        raise ValueError("ERROR: The secret stored in AWS is not valid JSON.")
    try:
        creds = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES
        )
    except Exception as e:
        print(f"Error creating gmail service: {e}")
        

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
    
    secret = get_secret()
    
    """Send a plain-text email via Gmail API using service account impersonation."""
    service = _get_gmail_service(secret)


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
    
# ---------------- Lambda entrypoint ----------------
def handler(event, _ctx):
    """
    Expected event shape:
    {
      "to_email": "citizen@example.com",
      "ticket_id": "12345678",
      "category": "Pothole",
      "description": "Large pothole near 5th & Main",
      "status": "Open",
      "submitted_at": "2025-09-05T12:34:00Z"    # optional ISO8601
    }

    """
    try:
        if isinstance(event, str):
            event = json.loads(event or "{}")
        elif not isinstance(event, dict):
            event = {}

        # mode = (event.get("mode") or "send_ticket_created_email").lower()

        # if mode == "send_ticket_created_email":
        submitted_at = event.get("submitted_at")
        dt = None
        if submitted_at:
            # accept simple ISO8601
            dt = datetime.fromisoformat(submitted_at.replace("Z", "+00:00")).replace(tzinfo=None)

        send_ticket_created_email(
            to_email=event["to_email"],
            ticket_id=event["ticket_id"],
            category=event.get("category"),
            description=event.get("description"),
            status=event.get("status", "Open"),
            submitted_at=dt,
        )
        
        return {
            "statusCode": 200,
            "body": json.dumps({"message": f"Confirmation email of ticket created has been sent to email ID: {event["to_email"]}"})
        }

        # elif mode == "send_email":
        #     result = _send_email(
        #         subject=event["subject"],
        #         text_body=event.get("text_body"),
        #         html_body=event.get("html_body"),
        #         recipient=event["to"],
        #         reply_to=IMPERSONATE_USER,
        #     )
        #     return result
        # else:
        #     return {"ok": False, "error": f"Unknown mode: {mode}"}

    except Exception as e:
        e = str(e)
        return {
            "statusCode": 400,
            "body": json.dumps({f"message": "Something went wrong: {e}"})
        }