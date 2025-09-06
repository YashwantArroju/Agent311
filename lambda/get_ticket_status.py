import os, json, datetime
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
tickets = dynamodb.Table(TICKETS_TABLE)

def handler(event, context):
    try:
        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body)
        elif body is None:
            body = event

        ticket_id = (body.get("ticket_id") or "").strip()
        if not ticket_id:
            return {"statusCode": 400, "body": "ticket_id required"}
        
        res = tickets.get_item(Key={"ticket_id": ticket_id})
        item = res.get("Item")
        if not item:
            return {"statusCode": 404, "body": "Ticket not found"}

        # compute ETA remaining (calendar days)
        eta_days = int(item.get("eta_days", 5))
        created_at = item.get("created_at")
        remaining = eta_days
        if created_at:
            try:
                created_date = datetime.datetime.fromisoformat(created_at).date()
                days_elapsed = (datetime.date.today() - created_date).days
                remaining = max(0, eta_days - max(0, days_elapsed))
            except Exception:
                pass

        payload = {
            "ticket_id": item["ticket_id"],
            "status": item.get("status", "Open"),
            "dept": item.get("dept"),
            "eta_days": remaining,
            "updated_at": item.get("updated_at"),
            "category": item.get("category"),
            "description": item.get("description"),
            "status_description": item.get("status_description"),
            # extras if you want them:
            # "address": item.get("address"),
            # "contact_email": item.get("contact_email"),
        }
        return {"statusCode": 200, "body": json.dumps(payload)}
    except Exception as e:
        return {"statusCode": 500, "body": f"get_ticket_status error: {e}"}