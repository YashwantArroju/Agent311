# send_real_email.py
import os
import sys
from datetime import datetime, UTC

# This allows the script to find the 'backend' module when run from the project root.
# Ensure your project structure is:
# /project_root
# |-- backend/
# |   |-- email.py
# |-- send_real_email.py
try:
    from lambdafunctions.email import send_ticket_created_email
except ImportError:
    print("Error: Could not import from 'backend.email'.")
    print("Please make sure you are running this script from the project's root directory.")
    sys.exit(1)

def main():
    """
    Sets up the details and calls the function to send a real 311 ticket email.
    """
    print("🚀 Attempting to send a 311 ticket confirmation email...")

    # --- 1. CONFIGURE YOUR EMAIL DETAILS ---
    # ⚠️ IMPORTANT: Replace with the actual recipient's email address.
    recipient_email = "gauravmodi2003@gmail.com"

    ticket_details = {
        "to_email": recipient_email,
        "ticket_id": "TICKET-98765",
        "category": "Graffiti Removal",
        "description": "Graffiti reported on the park wall at the corner of Main St and 1st Ave.",
        "status": "Open",
        "submitted_at": datetime.now(UTC), # Uses a modern, timezone-aware timestamp
        "city": "Metroville",
    }

    # --- 2. VALIDATE ENVIRONMENT ---
    # The functions in email.py depend on these environment variables.
    # if not os.getenv("GMAIL_SA_FILE") or not os.getenv("GMAIL_IMPERSONATE"):
    #     print("\n❌ ERROR: Missing required environment variables.")
    #     print("Please set GMAIL_SA_FILE and GMAIL_IMPERSONATE before running.")
    #     print("\nExample for Linux/macOS:")
    #     print("  export GMAIL_SA_FILE='backend/credentials/service_account.json'")
    #     print("  export GMAIL_IMPERSONATE='your-account-to-impersonate@yourdomain.com'")
    #     print("\nExample for Windows (Command Prompt):")
    #     print('  set GMAIL_SA_FILE="backend\\credentials\\service_account.json"')
    #     print('  set GMAIL_IMPERSONATE="your-account-to-impersonate@yourdomain.com"')
        # sys.exit(1)

    # --- 3. SEND THE EMAIL ---
    try:
        print(f"\nSending email to: {ticket_details['to_email']}")
        # print(f"Impersonating user: {os.getenv('GMAIL_IMPERSONATE')}")
        
        # This is the call to your function
        result = send_ticket_created_email(**ticket_details)

        print("\n✅ Email sent successfully!")
        print("---------------------------------")
        print(f"  Message ID: {result.get('messageId')}")
        print(f"  From: {result.get('from')}")
        print(f"  To: {result.get('to')}")
        print(f"  Subject: {result.get('subject')}")
        print("---------------------------------")

    except FileNotFoundError as e:
        print(f"\n❌ ERROR: Credentials file not found.")
        print(f"  Details: {e}")
        print("  Please ensure the path set in the GMAIL_SA_FILE environment variable is correct.")
    except Exception as e:
        # Catches other potential issues, like authentication or API permission errors.
        print(f"\n❌ An unexpected error occurred: {e}")
        print("\nThis could be due to several reasons:")
        print("  - The Gmail API is not enabled in your Google Cloud project.")
        print("  - The service account does not have Domain-Wide Delegation set up correctly.")
        print("  - The impersonated user does not exist or has a suspended account.")

if __name__ == "__main__":
    main()