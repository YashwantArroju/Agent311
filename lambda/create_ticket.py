import os, json, uuid, datetime
import boto3


# Check for the local endpoint environment variable
DYNAMODB_ENDPOINT = os.environ.get('DYNAMODB_ENDPOINT')

# Initialize the client
dynamodb = boto3.resource(
    'dynamodb', 
    region_name='us-east-1',
    endpoint_url=DYNAMODB_ENDPOINT
)

TICKETS_TABLE = os.environ.get('TICKETS_TABLE', 'tickets')

DEFAULT_ETA_DAYS = int(os.getenv("DEFAULT_ETA_DAYS", "5"))

tickets = dynamodb.Table(TICKETS_TABLE)

def _now_iso():
    return datetime.datetime.utcnow().isoformat()

def handler(event, context):
    try:
        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body)
        elif body is None:
            body = event  # allow direct invoke with JSON

        category = (body.get("category") or "").strip()
        description = (body.get("description") or "").strip()
        address = (body.get("address") or "").strip()
        contact_email = (body.get("contact_email") or "").strip()

        if not (category and description and address and contact_email):
            return {"statusCode": 400, "body": "Missing required fields."}

        ticket_id = uuid.uuid4().hex[:8]
        now = _now_iso()

        tickets.put_item(Item={
            "ticket_id": ticket_id,
            "category": category,
            "description": description,
            "address": address,
            "contact_email": contact_email,
            "dept": _route_dept(category),
            "status": "Open",
            "status_description": "",
            "eta_days": DEFAULT_ETA_DAYS,
            "created_at": now,
            "updated_at": now,
        })

        # events.put_item(Item={
        #     "ticket_id": ticket_id,
        #     "created_at": now,   # sort key
        #     "event_type": "created",
        #     "payload": json.dumps({"category": category})
        # })
        
        print("Successful!")

        return {
            "statusCode": 200,
            "body": json.dumps({"ticket_id": ticket_id, "status": "Open", "eta_days": DEFAULT_ETA_DAYS})
        }
    except Exception as e:
        return {"statusCode": 500, "body": f"create_ticket error: {e}"}

def _route_dept(category: str) -> str:
    m = {
        "pothole": "Public Works",
        "streetlight": "Transportation",
        "missed_trash": "Sanitation",
        "graffiti": "Public Works",
        "noise": "Code Enforcement",
        "bulk_pickup": "Sanitation",
    }
    return m.get((category or "").lower(), "311 Intake")