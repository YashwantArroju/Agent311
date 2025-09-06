import json

_FAQ = [
    {"q": "missed trash", "a": "For missed trash, keep bins curbside; re-collection is often the next business day. If you’d like, I can create a service ticket to alert the sanitation team."},
    {"q": "pothole", "a": "Potholes are typically handled by public works. Repairs often take a few days once logged. Want me to create a ticket with the location and a short description?"},
    {"q": "streetlight", "a": "For a streetlight outage, it generally takes 3–5 business days to fix. I can create a ticket for you now."},
    {"q": "noise", "a": "Most places have quiet hours (~10PM–7AM). Non-emergency noise concerns can be logged. Shall I create a ticket to document the times and location?"},
    {"q": "bulk pickup", "a": "Bulk items (e.g., sofa, mattress) usually need scheduled pickup. If you’d like, I can create a ticket to start the request."},
]

def handler(event, context):
    try:
        body = event.get("body")
        if isinstance(body, str):
            body = json.loads(body)
        elif body is None:
            body = event
        q = (body.get("query") or "").lower()
        for item in _FAQ:
            if item["q"] in q:
                return {"statusCode": 200, "body": json.dumps({"answer": item["a"], "source": "Generic FAQs"})}
        return {"statusCode": 200, "body": json.dumps({"answer": None, "source": None})}
    except Exception as e:
        return {"statusCode": 500, "body": f"search_kb error: {e}"}