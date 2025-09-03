docker network create sam-local-network
docker run -p 8000:8000 --network sam-local-network --name dynamodb-local -d amazon/dynamodb-local
docker ps
aws dynamodb list-tables --endpoint-url http://localhost:8000
aws dynamodb create-table --cli-input-json file://tickets-create-schema.json --endpoint-url http://dynamodb-local:8000
sam local invoke CreateTicket --event create_ticket_event.json --env-vars env.json --docker-network sam-local-network
sam local invoke GetTicketStatus --event get_ticket_status_event.json --env-vars env.json --docker-network sam-local-network
sam local invoke SearchKb --event search_kb_event.json --docker-network sam-local-network