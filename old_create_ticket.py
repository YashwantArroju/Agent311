# Old create_ticket
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

def handler(event, context):
    """
    Creates a new ticket object in the DynamoDB table.
    """
    
    # Extract ticket details from the incoming event
    ticket_id = str(uuid.uuid4())   # event.get('id')  # Using uuid to generate unique IDs
    
    address = event.get('address')
    category = event.get('category')
    dept = event.get('dept')
    description = event.get('description')
    contact_email = event.get('contact_email')
    # created_at = time.time()
    created_at = '02/02/2025' # Gets seconds since epoch
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