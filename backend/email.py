# backend/email.py
from google.oauth2 import service_account
from googleapiclient.discovery import build
from email.mime.text import MIMEText
import base64

# Path to service account JSON
SERVICE_ACCOUNT_FILE = "service_account.json"

# Scopes needed
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# User you want to impersonate (must be in your Workspace domain)
IMPERSONATE_USER = "AiAgent@lightningminds.com"

def get_gmail_service():
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )
    delegated_creds = creds.with_subject(IMPERSONATE_USER)
    service = build("gmail", "v1", credentials=delegated_creds)
    return service

def send_email(subject, body, recipient):
    service = get_gmail_service()
    message = MIMEText(body)
    message["to"] = recipient
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    
    send_message = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    
    return f"Email sent to {recipient}, message ID: {send_message['id']}"
