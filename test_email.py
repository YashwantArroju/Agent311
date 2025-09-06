# test_email.py
import unittest
import os
import json
import base64
from datetime import datetime
from unittest.mock import patch, MagicMock

from lambdafunctions import email

class TestEmailFunctions(unittest.TestCase):
    """
    Test suite for the email sending functionalities in lambdafunctions/email.py.
    """

    def setUp(self):
        """Set up the test environment before each test method runs."""
        # Define dummy environment variables for testing
        self.test_sa_file = "lambdafunctions/service_account.json"
        self.test_impersonate_user = "aiagent@lightningminds.com"
        self.test_city_name = "City"
        print("1")
        os.environ["GMAIL_SA_FILE"] = self.test_sa_file
        os.environ["GMAIL_IMPERSONATE"] = self.test_impersonate_user
        os.environ["CITY_NAME"] = self.test_city_name
        print("2")

        # Create a dummy service account file and its directory to avoid FileNotFoundError
        print("3")
        os.makedirs(os.path.dirname(self.test_sa_file), exist_ok=True)
        print("4")
        with open(self.test_sa_file, "w") as f:
            json.dump({"client_email": "dummy@example.com", "private_key": "key"}, f)
        print("5")
        
        # Reset the global service variable in the email module to ensure test isolation
        email._service = None

    def tearDown(self):
        """Clean up the test environment after each test method runs."""
        # Remove the dummy file and directory
        if os.path.exists(self.test_sa_file):
            os.remove(self.test_sa_file)
        
        dir_name = os.path.dirname(self.test_sa_file)
        # Clean up directory only if it's empty
        if os.path.exists(dir_name) and not os.listdir(dir_name):
            os.rmdir(dir_name)
            # Clean up parent 'lambdafunctions' dir if it's also empty
            parent_dir = os.path.dirname(dir_name)
            if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                 os.rmdir(parent_dir)


        # Unset the environment variables
        del os.environ["GMAIL_SA_FILE"]
        del os.environ["GMAIL_IMPERSONATE"]
        del os.environ["CITY_NAME"]
        
        # Reset the global service again for good measure
        email._service = None

    # --- Tests for compose_city311_plaintext ---
    
    def test_compose_city311_plaintext_all_fields(self):
        """🧪 Tests composing the email body with all fields provided."""
        test_time = datetime(2025, 9, 5, 12, 30, 0)
        body = email.compose_city311_plaintext(
            city="Testville",
            category="Pothole",
            description="A large pothole on Main St.",
            ticket_id="T123",
            status="Open",
            submitted_at=test_time,
        )
        self.assertIn("Thank you for contacting Testville 311.", body)
        self.assertIn("Category: Pothole", body)
        self.assertIn("Ticket: T123", body)
        self.assertIn("Description: A large pothole on Main St.", body)
        self.assertIn("Status: Open", body)
        self.assertIn("Date Submitted: 9/5/2025", body)

    def test_compose_city311_plaintext_missing_optional_fields(self):
        """🧪 Tests that missing optional fields are replaced with a hyphen."""
        body = email.compose_city311_plaintext(
            city="Metroburg",
            category=None,
            description=None,
            ticket_id=456,
            status="In Progress",
            submitted_at=datetime.now(),
        )
        self.assertIn("Category: -", body)
        self.assertIn("Description: -", body)

    @patch('lambdafunctions.email.datetime')
    def test_compose_city311_plaintext_no_timestamp_fallback(self, mock_datetime):
        """🧪 Tests that the current UTC time is used when submitted_at is None."""
        mock_datetime.utcnow.return_value = datetime(2025, 1, 1)
        
        body = email.compose_city311_plaintext(
            city="Testville",
            category="Graffiti",
            ticket_id="789",
            status="Closed",
            description="Graffiti on park bench",
            submitted_at=None,
        )
        self.assertIn("Date Submitted: 1/1/2025", body)
        mock_datetime.utcnow.assert_called_once()

    # --- Tests for _get_gmail_service ---

    def test_get_gmail_service_file_not_found(self):
        """🧪 Tests that FileNotFoundError is raised if the credentials file is missing."""
        os.remove(self.test_sa_file) # Remove the file to trigger the error
        with self.assertRaises(FileNotFoundError):
            email._get_gmail_service()

    @patch('lambdafunctions.email.build')
    @patch('lambdafunctions.email.service_account.Credentials')
    def test_get_gmail_service_builds_and_caches_service(self, mock_creds, mock_build):
        """🧪 Tests that the Gmail service is built correctly and cached on subsequent calls."""
        # First call should build the service
        service_instance_1 = email._get_gmail_service()
        
        # Check that the build process was called with the correct parameters
        mock_creds.from_service_account_file.assert_called_with(
            self.test_sa_file, scopes=email.SCOPES
        )
        mock_creds.from_service_account_file.return_value.with_subject.assert_called_with(
            self.test_impersonate_user
        )
        mock_build.assert_called_once()
        self.assertEqual(service_instance_1, mock_build.return_value)
        
        # Second call should return the cached service without rebuilding
        service_instance_2 = email._get_gmail_service()
        
        # Assert that build was NOT called a second time
        mock_build.assert_called_once()
        self.assertEqual(service_instance_1, service_instance_2)

    # --- Tests for send_email_sa ---

    @patch('lambdafunctions.email._get_gmail_service')
    def test_send_email_sa_constructs_and_sends_message(self, mock_get_service):
        """🧪 Tests that an email is correctly formatted, encoded, and sent via the API."""
        mock_service = MagicMock()
        mock_get_service.return_value = mock_service
        api_response = {"id": "message_abc123"}
        mock_service.users().messages().send().execute.return_value = api_response
        
        recipient = "gauravmodi2003@gmail.com"
        subject = "Test Subject"
        body = "This is a test body."
        
        result = email.send_email_sa(
            subject=subject,
            text_body=body,
            recipient=recipient,
            reply_to="reply-to@example.com"
        )

        mock_get_service.assert_called_once()
        mock_service.users().messages().send.assert_called_once()
        
        # Decode the raw message from the API call to inspect its content
        _, kwargs = mock_service.users().messages().send.call_args
        raw_msg_encoded = kwargs['body']['raw']
        raw_msg_decoded = base64.urlsafe_b64decode(raw_msg_encoded).decode('utf-8')

        self.assertIn(f"to: {recipient}", raw_msg_decoded)
        self.assertIn(f"subject: {subject}", raw_msg_decoded)
        self.assertIn(f"from: {self.test_city_name} 311 Team <{self.test_impersonate_user}>", raw_msg_decoded)
        self.assertIn("Reply-To: reply-to@example.com", raw_msg_decoded)
        self.assertIn("\n\nThis is a test body.", raw_msg_decoded)
        
        # Check that the function returns the expected dictionary
        self.assertEqual(result['messageId'], 'message_abc123')
        self.assertEqual(result['to'], recipient)

    # --- Tests for send_ticket_created_email ---

    @patch('lambdafunctions.email.send_email_sa')
    def test_send_ticket_created_email_orchestration(self, mock_send_email_sa):
        """🧪 Tests the high-level function that orchestrates email creation and sending."""
        email.send_ticket_created_email(
            to_email="requester@example.com",
            ticket_id="TICKET-XYZ",
            category="Streetlight Outage",
            description="Light is out at Oak & Pine.",
            status="New"
        )
        
        mock_send_email_sa.assert_called_once()
        _, kwargs = mock_send_email_sa.call_args
        
        # Check that the correct arguments were passed to the sender function
        expected_subject = f"{self.test_city_name} 311 – Case Received (Ticket #TICKET-XYZ)"
        self.assertEqual(kwargs['subject'], expected_subject)
        self.assertEqual(kwargs['recipient'], "requester@example.com")
        self.assertEqual(kwargs['reply_to'], self.test_impersonate_user)
        self.assertIn("Category: Streetlight Outage", kwargs['text_body'])
        self.assertIn("Description: Light is out at Oak & Pine.", kwargs['text_body'])


if __name__ == '__main__':
    unittest.main(verbosity=2)