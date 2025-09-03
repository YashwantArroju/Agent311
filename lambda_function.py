from create_ticket import create_ticket
# from get_ticket_status import get_ticket_status

import json

def get_named_parameter(event, name):
    if name not in event:
        return None

    return event.get(name)

def handler(event, context):
    print(f"Event: {event}")
    print(f"Context: {context}")

    extended_tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
    resource = extended_tool_name.split("___")[1]
    
    print(resource)
    
    if resource == "create_ticket":
        address = get_named_parameter(event=event, name="address")
        category = get_named_parameter(event=event, name="category")
        dept = get_named_parameter(event=event, name="dept") # Delete later if needed
        description = get_named_parameter(event=event, name="description")
        contact_email = get_named_parameter(event=event, name="contact_email")
        
        if not address:
            return {
                'statusCode': 400,
                "body": "❌ Please provide address",
                # 'body': json.dumps({'message': 'Address is required'})
            }
            
        if not category:
            return {
                'statusCode': 400,
                "body": "❌ Please provide category",
                # 'body': json.dumps({'message': 'Category is required'})
            }
            
        # Should description be allowed to be empty?
        if not description:
            return {
                'statusCode': 400,
                "body": "❌ Please provide description",
                # 'body': json.dumps({'message': 'Description is required'})
            }
            
        if not contact_email:
            return {
                'statusCode': 400,
                "body": "❌ Please provide email",
                # 'body': json.dumps({'message': 'Email is required'})
            }
            
        try:
            res = create_ticket(
                
            )