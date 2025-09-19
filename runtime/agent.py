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
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.memory import ConversationBufferMemory
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from pathlib import Path
from typing import Dict, Optional


### CRITICAL: OTEL_PYTHON_DISABLED_INSTRUMENTATIONS must be set to botocore in Runtime environment variables  ###

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
load_dotenv(dotenv_path=ENV_PATH)

### LOGGING SETUP ###
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)
#####################


print("Starting up...")


MEMORY_ID = os.getenv("MEMORY_ID", "Memory311Agent-wZTZP0772X")
GATEWAY_SECRET_NAME = os.getenv("GATEWAY_SECRET_NAME", "agentcore/cityassist311/gateway")

SYSTEM_PROMPT = """
    You are CityAssist, a helpful city 311-style non-emergency assistant for the city of Cityville. 
	
    CORE BEHAVIOR
        - ALWAYS CHECK MEMORY/CHAT HISTORY TO SEE IF YOU HAVE THE INFORMATION YOU NEED ALREADY PROVIDED
        - Never re-ask for information that is already present in the current user message OR in chat_history.
 
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
        - For service questions (garbage collection, street maintenance, pets, water/sewage etc.):
            1. Call the target-knowledge-base___search_kb with the user’s query and get the results
            2. Once you have the results:
                - If the result is empty, it is very important for you to respond with "Sorry, this is out of my knowledge base"
                - If the answer is not found in the results, it is very important for you to respond with "Sorry, this is out of my knowledge base"
            3. If the results provided are relevant, give a concise answer.
                - Answer only using the results provided. Your response should only be about the question asked and nothing else.
                - Only use the information relevant to the user's query from the results
            4. Then IMMEDIATELY offer to create a ticket.
            5. If the user agrees (e.g., “yes”, “please do”, “create it”), PROCEED to reporting the issue using target-create-ticket___create_ticket.
        
        - Give a concise, general answer. Then IMMEDIATELY offer to create a ticket.

	GUARDRAILS
	- If the message suggests an emergency, say: "Call 911 now." Do not call any tools. 
 """

class Agent:
    
    def __init__(self):
        """Initializes the Agent, setting up session and memory attributes."""
        self.session: Optional[ClientSession] = None
        self._memory_client = None
        self._memory = None
        self._gateway_session_context = None
        self._gateway_streams_context = None
        
        self._cached_token: Optional[str] = None
        self._token_expiry: float = 0.0

        
    def get_memory_instance_id(self) -> str:
        """
        Retrieves the ID of an active AgentCore memory instance.

        It checks for an existing, active memory instance matching the MEMORY_ID.
        If none is found, it triggers the creation of a new memory instance.

        :return: The ID of the memory instance.
        :rtype: str
        """
        
        found = False
        
        if self._memory_client:
            for memory in self._memory_client.list_memories():
                if MEMORY_ID == memory.get('id') and memory.get('status') == 'ACTIVE':
                    found = True
                    self._memory = memory
                    return memory.get('id')
                
            if not found:
                return self.create_memory_instance()
                
        else:
            print(f"❌ Memory client not valid. Can't retrieve memory!")
        
        
    def _load_gateway_cfg(self) -> Dict[str, str]:
        """
        Loads AgentCore Gateway secrets.

        This method first attempts to load configuration from environment variables.
        If they are not all present, it falls back to fetching them from AWS Secrets Manager.

        :return: A dictionary containing gateway and Cognito configuration.
        :rtype: Dict[str, str]
        :raises ValueError: If a required key is missing from the fetched secret.
        """
        env = {
            "gateway_url": os.getenv("GATEWAY_URL"),
            "token_url": os.getenv("COGNITO_TOKEN_URL"),
            "client_id": os.getenv("COGNITO_CLIENT_ID"),
            "client_secret": os.getenv("COGNITO_CLIENT_SECRET"),
        }
        if all(env.values()):
            print(f"⚙️ Loaded Gateway/Cognito config from environment.")
            return env

        sm = boto3.client("secretsmanager")
        val = sm.get_secret_value(SecretId=GATEWAY_SECRET_NAME)["SecretString"]
        cfg = json.loads(val)
        print(f"⚙️ Loaded Gateway/Cognito config from Secrets Manager: {GATEWAY_SECRET_NAME}")

        for k in ("gateway_url", "token_url", "client_id", "client_secret"):
            if not cfg.get(k):
                raise ValueError(f"Secret missing required key: {k}")
        if not cfg["token_url"].endswith("/oauth2/token"):
            raise ValueError("token_url must end with '/oauth2/token'.")
        return cfg
    
    
    def _fetch_access_token(self, cfg: Dict[str, str]) -> str:
        """
        Fetches an OAuth2 access token for gateway authentication.

        The token is cached with its expiry time to avoid redundant requests. A new
        token is fetched only if the current one is missing or close to expiring.

        :param cfg: A dictionary with Cognito client credentials and token URL.
        :type cfg: Dict[str, str]
        :return: The access token string.
        :rtype: str
        :raises RuntimeError: If the token request fails.
        """
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
        """
        Establishes a connection to the MCP Gateway.

        :param config: Dictionary containing the gateway URL.
        :type config: Dict[str, str]
        :param access_token: The JWT access token for authorization.
        :type access_token: str
        :raises RuntimeError: If the gateway URL or access token is missing.
        """
        if not config.get("gateway_url") or not access_token:
            raise RuntimeError("❌ Missing GATEWAY_URL or GATEWAY_ACCESS_TOKEN")

        print(f"🔌 Connecting to Gateway at {config.get("gateway_url")}...")

        self._gateway_streams_context = streamablehttp_client(config.get("gateway_url"), headers={"Authorization": f"Bearer {access_token}"})
        read_stream, write_stream, _ = await self._gateway_streams_context.__aenter__()

        self._gateway_session_context = ClientSession(read_stream, write_stream)
        self.session: ClientSession = await self._gateway_session_context.__aenter__()
        await self.session.initialize()
        
    
    async def get_tools(self):
        """
        Retrieves executable tools from the connected gateway session.

        :return: A list of loaded LangChain tool objects.
        :rtype: list
        """
        tools = await load_mcp_tools(self.session)
        
        print("🛠️  Tools loaded successfully:")
        for tool in tools:
            print(f"- {tool.name}")
        
        return tools
    
    def connect_to_memory_client(self):
        """Initializes the connection to the Bedrock AgentCore Memory service."""
        print("🔌 Creating memory client...")
        self._memory_client = MemoryClient(region_name="us-east-1")
        
    def create_memory_instance(self) -> str:
        """
        Creates a new Bedrock AgentCore memory instance with predefined settings.

        :return: The ID of the newly created memory instance.
        :rtype: str
        :raises Exception: If memory creation fails.
        """
        try:
            self._memory = self._memory_client.create_memory_and_wait(
                name="Memory311Agent",
                description="Conversational memory for 311 agent",
                strategies=[],           # No memory strategies for short-term memory
                event_expiry_days=7,     # Memories expire after 7 days
                max_wait=300,            # Maximum time to wait for memory creation (5 minutes)
                poll_interval=10         # Check status every 10 seconds
            )
            return self._memory.get('id')
            
        except Exception as e:
            print(f"❌ Failed to create memory instance: {e}")
            raise
    
    
    def get_conversation(self, actor_id: str, session_id: str):
        """
        Retrieves conversation history from AgentCore Memory.

        :param actor_id: The identifier for the user.
        :type actor_id: str
        :param session_id: The identifier for the current conversation session.
        :type session_id: str
        :return: A list of past conversation events.
        :rtype: list
        """
        if not self._memory_client: 
            self.connect_to_memory_client()
        memory_id = self.get_memory_instance_id()
        events = self._memory_client.list_events(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=session_id,
                max_results=10
            )
        
        return events
        
    def save_conversation(self, actor_id: str, session_id: str, conversation: list):
        """
        Saves a turn of the conversation to AgentCore Memory.

        :param actor_id: The identifier for the user.
        :type actor_id: str
        :param session_id: The identifier for the current conversation session.
        :type session_id: str
        :param conversation: A list of message tuples (content, role) to be saved.
        :type conversation: list
        """
        if not self._memory_client: 
            self.connect_to_memory_client()
        memory_id = self.get_memory_instance_id()
        self._memory_client.create_event(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=conversation
        )


    async def create_agent(self, actor_id: str, session_id: str) -> AgentExecutor:
        """
        Creates and configures the LangChain agent executor.

        This method sets up the LLM, connects to the gateway to load tools,
        and initializes conversation memory with history from the specified session.

        :param actor_id: The identifier for the user.
        :type actor_id: str
        :param session_id: The identifier for the current conversation session.
        :type session_id: str
        :return: A configured AgentExecutor instance.
        :rtype: AgentExecutor
        """
        llm = ChatBedrock(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            model_kwargs={"temperature": 0.0},
        )
        
        # Get Gateway secrets and connect
        config = self._load_gateway_cfg()
        access_token = self._fetch_access_token(config)
        await self.connect_to_gateway(config, access_token)
        tools = await self.get_tools()
        
        # Connect to AgentCore Memory and get history
        if not self._memory_client: 
            self.connect_to_memory_client()
        past_events = self.get_conversation(actor_id=actor_id, session_id=session_id)
        
        # Create memory buffer
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
        
        # Load past events into the memory buffer
        if past_events:
            for event in reversed(past_events):
                if 'payload' in event:
                    input_text, output_text = "", ""
                    for message_turn in event['payload']:
                        if 'conversational' in message_turn:
                            role = message_turn['conversational'].get('role')
                            content = message_turn['conversational'].get('content', {}).get('text', '')
                            if role == "USER":
                                input_text = content
                            elif role == "ASSISTANT":
                                output_text = content
                    if input_text and output_text:
                        memory.save_context({"input": input_text}, {"output": output_text})
        
        # Create the prompt template
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="chat_history"),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        )
        
        # Create the agent and executor
        agent = create_tool_calling_agent(llm, tools, prompt)
        executor = AgentExecutor(
            agent=agent, 
            tools=tools, 
            verbose=True, 
            handle_parsing_errors=True,
            memory=memory
        )
        return executor
    
    
    async def process_query(self, user_query: str, actor_id: str, session_id: str) -> str:
        """
        Processes a user query through the agent.

        This is the main orchestration method. It creates the agent, invokes it
        with the user's query, gets the response, and saves the new conversation
        turn to memory.

        :param user_query: The user's input string.
        :type user_query: str
        :param actor_id: The identifier for the user.
        :type actor_id: str
        :param session_id: The identifier for the current conversation session.
        :type session_id: str
        :return: The agent's final text response.
        :rtype: str
        """
        agent_executor = await self.create_agent(actor_id, session_id)
        
        result = await agent_executor.ainvoke({"input": user_query})
        raw_response = result["output"]
        
        response_text = ""
        if isinstance(raw_response, list) and raw_response and isinstance(raw_response[0], dict) and "text" in raw_response[0]:
            response_text = raw_response[0]["text"]
        else:
            # Fallback for when the output is already a string or another type.
            response_text = str(raw_response)
        
        # Save the new conversation turn to memory
        conversation = [
            (user_query, "USER"),
            (response_text, "ASSISTANT")
        ]
        self.save_conversation(actor_id=actor_id, session_id=session_id, conversation=conversation)
        
        return response_text

        
    async def cleanup(self):
        """Gracefully closes gateway connections to release resources."""
        print("Cleaning up resources...")
        if self._gateway_session_context:
            await self._gateway_session_context.__aexit__(None, None, None)
        if self._gateway_streams_context:
            await self._gateway_streams_context.__aexit__(None, None, None)
        print("Cleanup complete.")


app = BedrockAgentCoreApp()

@app.entrypoint
async def agent_invocation(payload: dict, context) -> dict:
    """
    Main entrypoint for the Bedrock AgentCore runtime.

    This function is called by the runtime for each invocation. It parses the
    user's prompt, processes it using the Agent class, and handles session
    management and error reporting.

    :param payload: The input data from the runtime, containing the user's prompt.
    :type payload: dict
    :param context: The runtime context object, containing session information.
    :type context: object
    :return: A dictionary containing the agent's response or an error message.
    :rtype: dict
    """
    print(f"SessionId: {context.session_id}")
    print(f"Received payload: {payload}")
    
    user_input = payload.get("prompt")
    client = None
    
    try:
        actor_id = "user"
        session_id = context.session_id
        
        if not session_id:
            session_id = "default_session"

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