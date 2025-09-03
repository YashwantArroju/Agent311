import os
import boto3
import json
import uuid
import time

# Check for the local endpoint environment variable
DYNAMODB_ENDPOINT = os.environ.get('DYNAMODB_ENDPOINT')

# Initialize the client
dynamodb = boto3.resource(
    'dynamodb', 
    region_name='us-east-1',
    endpoint_url=DYNAMODB_ENDPOINT
)

# Get the table name from an environment variable
TABLE_NAME = os.environ.get('TABLE_NAME', 'tickets')
table = dynamodb.Table(TABLE_NAME)

def create_ticket(
    address: str = None, category: str = None, description: str = None, contact_email: str = None
) -> str:
    """
    Creates a new support ticket.

    Args:
        address (str, required): Address/location of the issue.
        category (str, required): Category to which the issue belongs.
        description (str, required): Description of the issue.
        contact_email (str, required): Contact email of the person reporting the issue.

    Returns:
        str: Ticket ID.

    """
    # Raises:
        # ClientError: If there's an issue with DynamoDB operations.
        # ValueError: If a required argument is missing, or invalid format.
    
    # Extract ticket details from the incoming event
    ticket_id = str(uuid.uuid4())   # event.get('id')  # Using uuid to generate unique IDs
    
    
    dept = "sanitation"
    
    created_at = time.time()        # Gets seconds since epoch
    eta_days = 5                    # Default value for now
    status = "open"                 # Default value


    try:
        # Create the item object to be saved in DynamoDB
        item_to_create = {
            'id': ticket_id,
            'address': address,
            'category': category,
            'dept': dept, # Get based on category (from frontend or decide here based on category?)
            'description': description,
            'contact_email': contact_email,
            'created_at': created_at, # Get programatically
            'eta_days': eta_days, # Default value for now? 5?
            'status': status, # Should be open by default
        }
        
        print("Attempting to connect to DynamoDB and create item...")

        # Use put_item to create or overwrite the item
        table.put_item(Item=item_to_create)

        print("Item created successfully!")

        return {
            'statusCode': 201,
            'body': json.dumps({
                'message': 'Ticket created successfully!',
                'ticket': item_to_create
            })
        }
    except Exception as e:
        print(e)
        return {
            'statusCode': 500,
            'body': json.dumps({'message': 'Error creating ticket'})
        }