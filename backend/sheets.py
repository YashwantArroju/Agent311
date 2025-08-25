from google.oauth2 import service_account
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SERVICE_ACCOUNT_FILE = "service_account.json"
IMPERSONATE_USER = "orders@yourdomain.com"  # Workspace user

# Load credentials
creds = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
delegated_creds = creds.with_subject(IMPERSONATE_USER)

# Sheets API client
sheets_service = build("sheets", "v4", credentials=delegated_creds)

# Drive API client
drive_service = build("drive", "v3", credentials=delegated_creds)

# Example: Read a spreadsheet
SPREADSHEET_ID = "your-sheet-id"
RANGE_NAME = "Sheet1!A1:D10"
result = sheets_service.spreadsheets().values().get(
    spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME
).execute()
rows = result.get("values", [])

# Example: List spreadsheets in Drive
results = drive_service.files().list(
    q="mimeType='application/vnd.google-apps.spreadsheet'",
    pageSize=10, fields="files(id, name)"
).execute()
files = results.get("files", [])
