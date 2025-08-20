# test_ticket.py
import requests

payload = {
    "category": "pothole",
    "description": "2 ft deep pothole in the right lane",
    "address": "421 Willingh Rd, near Walmart",
    "contact_email": "we@gmail.com",
    "contact_phone": ""
}

r = requests.post("http://localhost:8011/create_ticket", json=payload, timeout=10)
print("STATUS", r.status_code)
print("BODY", r.text)
