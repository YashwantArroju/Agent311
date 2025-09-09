import boto3
import json
import logging
import os
import requests
import sys
import time

from bedrock_agentcore.memory import MemoryClient
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from dotenv import load_dotenv
from langchain_aws import ChatBedrock
from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import AgentExecutor, create_tool_calling_agent
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pathlib import Path
from typing import Dict, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

print("Starting up...")

### CRITICAL: OTEL_PYTHON_DISABLED_INSTRUMENTATIONS must be set to botocore in Runtime environment variables  ###

# from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
# BotocoreInstrumentor().instrument()
# OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=botocore
# os.environ['OTEL_PYTHON_DISABLED_INSTRUMENTATIONS'] = 'botocore'
# os.environ["LANGSMITH_OTEL_ENABLED"] = "true"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

    #     - list_memory_events
    # You MUST always follow the guidelines below.
    # <guidelines>
    #     - You MUST call the list_memory_events tool at every turn to see if there is any relevant information that can help in completing the
    #     current task.
    # </guidelines>

    # Greet the user and ask the user if they'd like to begin by reporting an issue, check ticket status, or any questions about city services. 
SYSTEM_PROMPT = """
    You are CityAssist, a helpful city 311-style non-emergency assistant for the city of Cityville. 
	
    You have access the following tools:
        - target-create-ticket___create_ticket
        - target-email___send_email
        - target-get-ticket-status___get_ticket_status
        - target-knowledge-base___search_kb
    
    Use the following user intentions to decide which tools to call:
        INTENTS → TOOLS
        - Report an issue → call target-create-ticket___create_ticket and then target-email___send_email
        - Check ticket status → call target-get-ticket-status___get_ticket_status
        - Ask about city services → call target-knowledge-base___search_kb
        
        REPORTING
        - To create ANY ticket, collect the following information one at a time:
            - First ask for Category,
            - Then ask for Description, Description can be ANY description string; do not block on perfect wording.
            - Next ask for Location (address or landmark), Location can be ANY location string; do not block on perfect addresses.
            - Finally, ask for Contact Email.
        - If the user has provided all four, you MUST call target-create-ticket___create_ticket and then target-email___send_email.
        - After creating a ticket, return ticket_id and ETA. A confirmation email was sent to {{contact_email}}.
        
        STATUS
        - If a ticket ID (8 characters) is present, call target-get-ticket-status___get_ticket_status and summarize status/ETA/department.
        - Otherwise, ask briefly for the ticket ID.
        
        KB
        - For service questions (missed trash, pothole, streetlight, noise etc.), you MUST call target-knowledge-base___search_kb with the user’s exact text. Do NOT answer from your own knowledge.
        - Give a concise, general answer. Then IMMEDIATELY offer to create a ticket.
        - If the user agrees (e.g., “yes”, “please do”, “create it”), PROCEED to collect ONLY the four fields and CALL target-create-ticket___create_ticket. Do NOT re-ask already provided info. Do NOT loop.

	GUARDRAILS
	- If the message suggests an emergency, say: "Call 911 now." Do not call any tools.
    - If you do not have the necessary information to process a request, politely ask them for the required information
    - Never assume any parameter values while using tools.
 """

    # - If you do not have the necessary information to process a request, politely ask them for the required information
# SYSTEM_PROMPT = """
#     You are CityAssist, a helpful city 311-style non-emergency assistant. 
#     You have access the following tools:
#         - list_memory_events
#         - target-create-ticket___create_ticket
#         - target-email___send_email
#         - target-get-ticket-status___get_ticket_status
#         - target-knowledge-base___search_kb
#     You MUST always follow the rules below.
    
#     Start by greeting the user and asking the user if they'd like to begin by reporting an issue, asking for ticket status, or if they have a general query about city services. 
#     You will ALWAYS follow the below general guidelines:
    
#     <guidelines>
#         - Always maintain a professional and helpful tone
#         - If the request suggests an emergency, respond: "Call 911 now." Do not call any tools.
#     </guidelines>
                
#     You have access to tools to: create a ticket, send an email, get ticket status, search KB (knowledge base), and list_memory_events tool
    
#     1. You MUST call the list_memory_events tool and see if there is any relevant information that you can use to complete your current task.
#     2. Use the following user intentions to decide which tools to call:
#         INTENTS → TOOLS
#         - Report an issue → call target-create-ticket___create_ticket and then target-email___send_email
#         - Check ticket status → call target-get-ticket-status___get_ticket_status
#         - Ask about city services → call target-knowledge-base___search_kb
        
#         REPORTING
#         - To create ANY ticket, collect exactly following four fields one at a time.
#         - First ask for Category,
#         - Then ask for Description, Description can be ANY description string; do not block on perfect wording.
#         - Next ask for Location (address or landmark), Location can be ANY location string; do not block on perfect addresses.
#         - Finally, ask for Contact Email.
#         - If the user has provided all four, you MUST call target-create-ticket___create_ticket and then target-email___send_email.
#         - After creating a ticket, return ticket_id and ETA. A confirmation email was sent to {{contact_email}}.
        
#         STATUS
#         - If a ticket ID (8 characters) is present, call target-get-ticket-status___get_ticket_status and summarize status/ETA/department.
#         - Otherwise, ask briefly for the ticket ID.
        
#         KB
#         - For service questions (missed trash, pothole, streetlight, noise etc.), you MUST call target-knowledge-base___search_kb with the user’s exact text. Do NOT answer from your own knowledge.
#         - Give a concise, general answer. Then IMMEDIATELY offer to create a ticket.
#         - If the user agrees (e.g., “yes”, “please do”, “create it”), PROCEED to collect ONLY the four fields and CALL create_ticket_tool. Do NOT re-ask already provided info. Do NOT loop.
# """

    # MEMORY CAPABILITIES:
    # - You have access to conversational with the list_memory_events tool. You MUST call it at the start of every turn and see if there is any relevant information that you can use to complete your current task.


MEMORY_ID = os.getenv("MEMORY_ID", "Memory311Agent-wZTZP0772X")
# GATEWAY_URL = os.getenv("GATEWAY_URL", "https://gateway-311-qms0ja1vyr.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp")
# GATEWAY_ACCESS_TOKEN = os.getenv("GATEWAY_ACCESS_TOKEN", "eyJraWQiOiJmN1lZV1ZIb05FaTBmMk9OcEE2akdtSSs2N3ZLTHE4TWRHbzM4RXY4V2NZPSIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiI0NHZmNnJ0cWM0YzM0anRyMGRwcDJkN3JycCIsInRva2VuX3VzZSI6ImFjY2VzcyIsInNjb3BlIjoiR2F0ZXdheS0zMTFcL2dlbmVzaXMtZ2F0ZXdheTppbnZva2UiLCJhdXRoX3RpbWUiOjE3NTczMDA5MTYsImlzcyI6Imh0dHBzOlwvXC9jb2duaXRvLWlkcC51cy1lYXN0LTEuYW1hem9uYXdzLmNvbVwvdXMtZWFzdC0xX1hFNXM2NnZpTCIsImV4cCI6MTc1NzMwNDUxNiwiaWF0IjoxNzU3MzAwOTE2LCJ2ZXJzaW9uIjoyLCJqdGkiOiJkMzRhZjhiMC01NjEyLTQ1ZTItOGZlMC05ZGU1ZDc0MDJmMDciLCJjbGllbnRfaWQiOiI0NHZmNnJ0cWM0YzM0anRyMGRwcDJkN3JycCJ9.CQb9JjpuBJGgFeqY-P-nYoVVizRY2lAgy8DnJDpGzjvCCMvzFkkMAhOxkC6pa2-Mcyb90eqB_juho_2qL430DZPDemTxRlvgDC3PnsLSVu6fZa6WqYt2GR5AhFtjkCwf9Lu-WQvd3EYLTGMnXRd2-A8FTb2tJy38le8vdvYnt4_fBptmaH0d4sc8UA2svFykHRAlcawkJAZhLXWKwHHhXCKy5fphGYOKbzUy6J7qk2ImanC-Z4xZamn_q9UEMs3r9M2jm2OQu6fB3By8aNdWFxlYjpJ5WtIYMO0jkTeKbw_kUi-ckunJk9oLb-5ozvGcjLd0DHrn2wawrx7gcQTQGw")
GATEWAY_SECRET_NAME = os.getenv("GATEWAY_SECRET_NAME", "agentcore/cityassist311/gateway")


class Agent:
    
    def __init__(self):
        """Initializes the Agent."""
        self.session: Optional[ClientSession] = None
        self._memory_client = None
        self._memory = None
        self._gateway_session_context = None
        self._gateway_streams_context = None
        
        self._cached_token: Optional[str] = None
        self._token_expiry: float = 0.0

        
    # You only need this if you don't already have a agentcore memory instance
    def connect_to_memory_client(self):
            
            print("🔌 Creating memory client...")
            self._memory_client = MemoryClient(region_name="us-east-1")
        
    def create_memory_instance(self) -> str:
        try:
            self._memory = self._memory_client.create_memory_and_wait(
                name="Memory311Agent",
                description="Conversational memory for 311 agent",
                strategies=[],           # No memory strategies for short-term memory
                event_expiry_days=7,     # Memories expire after 7 days
                max_wait=300,            # Maximum time to wait for memory creation (5 minutes)
                poll_interval=10         # Check status every 10 seconds
                
                ### Add for long-term memory later
                # strategies=[{
                #     "userPreferenceMemoryStrategy": {
                #         "name": "UserPreference",
                #         "namespaces": ["/users/{actorId}"]
                #     }
                # }]
                ###
            )
            
        except Exception as e:
            print(f"❌ Failed to create memory instance: {e}")
    
    # Returns memory ID of current memory instance
    def get_memory_instance_id(self) -> str:
        
        found = False
        
        if self._memory_client:
            for memory in self._memory_client.list_memories():
                if MEMORY_ID == memory.get('id') and memory.get('status') == 'ACTIVE':
                    found = True
                    self._memory = memory
                    # print(f"Memory ID: {memory.get('id')}")
                    # print(f"Memory: {memory}")
                    # print("--------------------------------------------------------------------")
                    return memory.get('id')
                
            if not found:
                return self.create_memory_instance()
                
        else:
            print(f"❌ Memory client not valid. Can't retrieve memory!")
        
    # Get Gateway secrets
    def _load_gateway_cfg(self) -> Dict[str, str]:
        env = {
            "gateway_url": os.getenv("GATEWAY_URL"),
            "token_url": os.getenv("COGNITO_TOKEN_URL"),
            "client_id": os.getenv("COGNITO_CLIENT_ID"),
            "client_secret": os.getenv("COGNITO_CLIENT_SECRET"),
        }
        if all(env.values()):
            print(f"[CFG] Loaded Gateway/Cognito config from environment.")
            return env

        sm = boto3.client("secretsmanager")
        val = sm.get_secret_value(SecretId=GATEWAY_SECRET_NAME)["SecretString"]
        cfg = json.loads(val)
        print(f"[CFG] Loaded Gateway/Cognito config from Secrets Manager: {GATEWAY_SECRET_NAME}")

        for k in ("gateway_url", "token_url", "client_id", "client_secret"):
            if not cfg.get(k):
                raise ValueError(f"Secret missing required key: {k}")
        if not cfg["token_url"].endswith("/oauth2/token"):
            raise ValueError("token_url must end with '/oauth2/token'.")
        return cfg
    
    
    def _fetch_access_token(self, cfg: Dict[str, str]) -> str:
        # global self._cached_token, self._token_expiry
        now = time.time()
        if self._cached_token and now < self._token_expiry - 60:
            return self._cached_token

        r = requests.post(
            cfg["token_url"],
            data={
                "grant_type": "client_credentials",
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=15,
        )
        if r.status_code != 200:
            raise RuntimeError(f"Token request failed: {r.status_code} {r.text}")
        body = r.json()
        self._cached_token = body["access_token"]
        self._token_expiry = now + int(body.get("expires_in", 3600))
        return self._cached_token
        
    
    async def connect_to_gateway(self, config: Dict[str, str], access_token: str):
        """Connects to the MCP Gateway."""
        if not config.get("gateway_url") or not access_token:
            raise RuntimeError("❌ Missing GATEWAY_URL or GATEWAY_ACCESS_TOKEN")

        print(f"🔌 Connecting to Gateway at {config.get("gateway_url")}...")

        self._gateway_streams_context = streamablehttp_client(config.get("gateway_url"), headers={"Authorization": f"Bearer {access_token}"})
        read_stream, write_stream, _ = await self._gateway_streams_context.__aenter__()

        self._gateway_session_context = ClientSession(read_stream, write_stream)
        self.session: ClientSession = await self._gateway_session_context.__aenter__()
        await self.session.initialize()
        
    
    async def get_tools(self):
        """Retrieves executable tools from the gateway session."""
        # Load MCP tools
        tools = await load_mcp_tools(self.session)
        
        print("🛠️  Tools loaded successfully:")
        for tool in tools:
            print(f"- {tool.name}")
        
        return tools
    
    
    async def cleanup(self):
        """Properly clean up the session and streams."""
        print("Cleaning up resources...")
        if self._gateway_session_context:
            await self._gateway_session_context.__aexit__(None, None, None)
        if self._gateway_streams_context:
            await self._gateway_streams_context.__aexit__(None, None, None)
        print("Cleanup complete.")


    async def create_agent(self, actor_id, session_id):
        """Creates and configures the LangGraph agent."""
        llm = ChatBedrock(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            model_kwargs={"temperature": 0.0},
        )
        
        
        ### CONNECT TO MEMORY AND GET EVENTS AS A TOOL ###
                
        # Get memories from the current region
        if not self._memory_client: 
            self.connect_to_memory_client()
        
        
        # @tool
        # def list_memory_events():
        #     """Tool used to retrieve conversation. This must be used.""" 
        #     print(f"\n\n\nMemoryID: {memory_id} \t\t ActorID: {actor_id} \t\t SessionID: {session_id}")
            
        #     events = self._memory_client.list_events(
        #             memory_id=memory_id,
        #             actor_id=actor_id,
        #             session_id=session_id,
        #             max_results=10
        #         )
        #     print(f"Events in the list_memory_events tool: {events}")
        #     return events
        
        ##################################################
        
        
        ### CONNECT TO GATEWAY AND GET TOOLS ###
        
        # Get Gateway secrets
        config = self._load_gateway_cfg()
        access_token = self._fetch_access_token(config)

        await self.connect_to_gateway(config, access_token)
        gateway_tools = await self.get_tools()
        
        ########################################
        
        tools = gateway_tools
        # tools = gateway_tools + [list_memory_events]

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{{input}}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        
        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)
        return executor
    
    def get_conversation(self, actor_id, session_id):
        if not self._memory_client: 
            self.connect_to_memory_client()
        memory_id = self.get_memory_instance_id()
        events = self._memory_client.list_events(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=session_id,
                max_results=10
            )
        
        # print(f"\n\nPast conversational events: {events}\n\n")
        
        return events
        
    def save_conversation(self, actor_id: str, session_id: str, conversation):
        if not self._memory_client: 
            self.connect_to_memory_client()
        memory_id = self.get_memory_instance_id()
        self._memory_client.create_event(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=conversation
        )

    # async def process_query(self, user_query: str, actor_id: str, session_id: str) -> str:
    #     """Process a query using the agent for a specific conversation thread."""
        
    #     # Get memory
    #     past_events = self.get_conversation(actor_id=actor_id, session_id=session_id)
    #     chat_history = []
    #     if past_events:
    #         for event in past_events:
    #             # Assuming event is a tuple like ('user input', 'USER') or ('agent response', 'ASSISTANT')
    #             message, sender = event
    #             if sender == "USER":
    #                 chat_history.append(HumanMessage(content=message))
    #             elif sender == "ASSISTANT":
    #                 chat_history.append(AIMessage(content=message))
        
    #     # Initialize the agent
    #     agent_executor = await self.create_agent(actor_id, session_id)
        
    #     # Prepare user query for agent
    #     # input = {"messages": [HumanMessage(content=user_query)]}
    #     result = await agent_executor.ainvoke({
    #         "input": user_query,
    #         "chat_history": chat_history
    #     })  
    #     # Invoke the agent
    #     # result = await agent_executor.ainvoke(input)
    #     # print(result)
    #     # result = final_state['messages'][-1].content
        
    #     raw_response = result["output"]
        
    #     response_text = ""
    #     if isinstance(raw_response, list) and raw_response and isinstance(raw_response[0], dict) and "text" in raw_response[0]:
    #         response_text = raw_response[0]["text"]
    #     else:
    #         # Fallback for when the output is already a string or another type.
    #         response_text = str(raw_response)
        
    #     # Save the memory
    #     conversation = [
    #         (user_query, "USER"),
    #         (response_text, "ASSISTANT")
    #     ]
    #     self.save_conversation(actor_id=actor_id, session_id=session_id, conversation=conversation)
        
    #     # past_conversation = self.get_conversation(actor_id=actor_id, session_id=session_id)
    #     # print(f"Past conversational events: {past_conversation}")
    #     # print(f"\n\nCurrent conversation: {conversation}\n\n")
        
    #     return response_text
    
    async def process_query(self, user_query: str, actor_id: str, session_id: str) -> str:
        """Process a query using the agent for a specific conversation thread."""
        
        # 1. Get previous conversation events from memory
        if not self._memory_client: 
            self.connect_to_memory_client()
            
        past_events = self.get_conversation(actor_id=actor_id, session_id=session_id)
        
        chat_history = []
        
        if past_events:
            for event in past_events:
                if 'payload' in event:
                    for message_turn in event['payload']:
                        if 'conversational' in message_turn:
                            role = message_turn['conversational'].get('role')
                            content = message_turn['conversational'].get('content', {}).get('text', '')
                            
                            if role == "USER":
                                chat_history.append(HumanMessage(content=content))
                            elif role == "ASSISTANT":
                                chat_history.append(AIMessage(content=content))

        # 2. Initialize the agent
        agent_executor = await self.create_agent(actor_id, session_id)
        
        # 3. Invoke the agent with current input AND past history
        result = await agent_executor.ainvoke({
            "input": user_query,
            "chat_history": chat_history
        })
        print(f"RESULT: {result}")
        raw_response = result["output"]
        print(f"RAW_RESPONSE: {raw_response}")
        
        response_text = ""
        if isinstance(raw_response, list) and raw_response and isinstance(raw_response[0], dict) and "text" in raw_response[0]:
            response_text = raw_response[0]["text"]
        else:
            # Fallback for when the output is already a string or another type.
            response_text = str(raw_response)
        print(f"RESPONSE_TEXT: {response_text}")
        
        # Save the memory
        conversation = [
            (user_query, "USER"),
            (response_text, "ASSISTANT")
        ]
        self.save_conversation(actor_id=actor_id, session_id=session_id, conversation=conversation)
        
        return response_text

        

app = BedrockAgentCoreApp()

@app.entrypoint
async def agent_invocation(payload, context):
    
    print(f"Context: {context}")
    
    print(f"Received payload: {payload}")
    
    user_input = payload.get("prompt")
    # user_input = (payload or {}).get("prompt") or (payload or {}).get("message") or "Hello"
    
    client = None
    
    try:
        # Get the unique session ID from the invocation context.
        # This will serve as our thread_id for conversation memory (short-term).
        actor_id = "user"
        session_id = context.session_id
        
        # Fallback for local testing or environments without a session_id
        if not session_id:
            session_id = "default-session-id"

        client = Agent()
        
        response = await client.process_query(user_input, actor_id=actor_id, session_id=session_id)
        return {"response": response}

    except RuntimeError as e:
        logging.error(f"Configuration Error: {e}")
        return {"error": str(e)}
        
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")
        return {"error": "An unexpected error occurred while processing your request."}

    finally:
        if client:
            await client.cleanup()
            
if __name__ == "__main__":
    app.run()