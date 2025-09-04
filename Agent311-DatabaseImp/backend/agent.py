import warnings
warnings.filterwarnings("ignore", message=r".*LangChain agents will continue to be supported.*")

# ---------- std imports ----------
import os
import re
import uuid
import json
import pathlib
import sqlite3
import requests
from dotenv import load_dotenv

# ---------- langchain / llm ----------
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

# ---------- langgraph ----------
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode             # executes @tool functions
from langgraph.checkpoint.sqlite import SqliteSaver # durable state (survives reloads)
from langgraph.graph.message import add_messages

# ---------- local gmail helper ----------
# Uses your backend/email.py service-account Gmail sender
from .email import send_ticket_created_email

# ============== Env / Config ==============
load_dotenv()
API_BASE = os.getenv("API_BASE", "http://localhost:8001")

# Load categories YAML once (we just embed the raw text in the prompt)
ROOT = pathlib.Path(__file__).resolve().parents[1]
CATS_PATH = ROOT / "config" / "categories.yaml"
try:
    CATS_YAML_TEXT = CATS_PATH.read_text(encoding="utf-8")
except FileNotFoundError as e:
    raise RuntimeError(
        f"Missing categories file at {CATS_PATH}. "
        "Create config/categories.yaml."
    ) from e

# ============== Emergency detection ==============
EMERGENCY_REGEX = r"(heart attack|gun|shots fired|fire in (my|the)|unconscious|not breathing|domestic violence|break[- ]?in|armed|stabbed|car crash with injuries)"
def is_emergency(text: str) -> bool:
    return bool(re.search(EMERGENCY_REGEX, text or "", re.IGNORECASE))

# ============== Tools (create auto-sends confirmation via Gmail) ==============
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

@tool
def create_ticket_tool(category: str, description: str, address: str = "", contact_email: str = "") -> str:
    """Create a city service ticket once you have: category, description, address, contact_email.
    Returns JSON with ticket_id/status/eta_days. Also auto-sends the confirmation email via Gmail."""
    if not contact_email or not re.search(EMAIL_RE, contact_email):
        return json.dumps({"error": "contact_email_missing_or_invalid",
                           "hint": "Ask for a valid email and call this tool again."})

    payload = {"category": category, "description": description, "address": address, "contact_email": contact_email}
    try:
        r = requests.post(f"{API_BASE}/create_ticket", json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return json.dumps({"error": "ticket_create_failed", "detail": str(e)})

    # Try to send the confirmation email using Gmail (no FastAPI email endpoint)
    email_meta = None
    try:
        email_meta = send_ticket_created_email(
            to_email=contact_email,
            ticket_id=data.get("ticket_id", "UNKNOWN"),
            category=category,
            description=description,
            status=data.get("status", "Open"),
        )
        data["confirmation_email_sent"] = True
        data["email_meta"] = email_meta
    except Exception as e:
        # Still return ticket details even if email fails
        data["confirmation_email_sent"] = False
        data["email_error"] = str(e)

    return json.dumps(data)

@tool
def get_ticket_status_tool(ticket_id: str) -> str:
    """Get status for an existing ticket_id. Returns JSON."""
    try:
        r = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": ticket_id}, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return json.dumps({"error": "status_lookup_failed", "detail": str(e)})

@tool
def search_kb_tool(query: str) -> str:
    """Search city FAQs/KB. Returns answer + source if found."""
    try:
        r = requests.post(f"{API_BASE}/search_kb", json={"query": query}, timeout=10)
        r.raise_for_status()
        return r.text
    except Exception as e:
        return json.dumps({"error": "kb_search_failed", "detail": str(e)})

@tool
def send_confirmation_tool(ticket_id: str, contact_email: str, category: str = "", description: str = "", status: str = "") -> str:
    """Resend the confirmation email for an existing ticket_id via Gmail.
    Requires contact_email. Optionally pass category/description/status for a richer email.
    If status is omitted, the tool will attempt to fetch it."""
    if not contact_email or not re.search(EMAIL_RE, contact_email):
        return json.dumps({"error": "contact_email_missing_or_invalid",
                           "hint": "Ask for a valid email and call this tool again."})
    # Fetch status if not supplied
    current_status = status
    if not current_status:
        try:
            rs = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": ticket_id}, timeout=8)
            if rs.ok:
                current_status = (rs.json() or {}).get("status", "Open")
        except Exception:
            current_status = "Open"

    try:
        meta = send_ticket_created_email(
            to_email=contact_email,
            ticket_id=ticket_id,
            category=(category or None),
            description=(description or None),
            status=current_status or "Open",
        )
        return json.dumps({"ticket_id": ticket_id, "resend": True, "email_meta": meta})
    except Exception as e:
        return json.dumps({"error": "email_send_failed", "detail": str(e), "ticket_id": ticket_id})

# ============== System prompt (updated to reflect Gmail flow) ==============
SYSTEM_PROMPT = f"""
You are CityAssist, a generic 311-style non-emergency assistant.

INTENTS → TOOLS
- Report an issue → call create_ticket_tool
- Check ticket status → call get_ticket_status_tool
- Ask about city services → call search_kb_tool

REPORTING
- To create ANY ticket, collect exactly the following four fields one at a time:
  1) Category, 2) Description, 3) Location (address or landmark), 4) Contact Email.
- If the user has provided all four, you MUST call create_ticket_tool immediately.
- NOTE: create_ticket_tool automatically sends the confirmation email via Gmail. You do NOT need to call send_confirmation_tool after creation.
  Only call send_confirmation_tool if the user asks to resend, and you MUST include both the ticket_id and contact_email.
- After creating a ticket, return ticket_id and ETA. Say that a confirmation email was sent to {{contact_email}} (or explain if it failed).

STATUS
- If a ticket ID (8 characters) is present, call get_ticket_status_tool and summarize status/ETA/department.
- Otherwise, ask briefly for the ticket ID.

KB
- For service questions (missed trash, pothole, streetlight, noise etc.), you MUST call search_kb_tool with the user’s exact text. Do NOT answer from your own knowledge.
- Give a concise, general answer. Then IMMEDIATELY offer to create a ticket.
- If the user agrees (e.g., “yes”, “please do”, “create it”), PROCEED to collect ONLY the four fields and CALL create_ticket_tool. Do NOT re-ask already provided info. Do NOT loop.

GUARDRAILS
- If the message suggests an emergency, say: "Call 911 now." Do not call any tools.
- Be concise, friendly, and action-oriented. Never ask for a phone number.
- Avoid repeating the same follow-up question more than once. If the user doesn’t provide a missing field after one ask, explain why it’s needed and stop.
- Do not invent data. If a required field is missing, ask for it directly.

You have access to the city's service taxonomy below. Use it to classify user requests and to know which fields to collect.

CATEGORIES_YAML:
---
{CATS_YAML_TEXT}
---
"""

# ============== LangGraph state ==============
from typing import TypedDict, List, Annotated
class ChatState(TypedDict):
    # Crucial: use add_messages so nodes append to history (LLM replies, ToolNode outputs, etc.)
    messages: Annotated[List[BaseMessage], add_messages]

# ============== Build the manual graph ==============
def build_graph(tools):
    # LLM bound to tools
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    llm_with_tools = llm.bind_tools(tools)

    # --- Node: chatbot (calls the model) ---
    def chatbot(state: ChatState):
        history = state["messages"]
        # Prepend system message for the *call*, but don't store it in state
        if not history or not isinstance(history[0], SystemMessage):
            msgs = [SystemMessage(content=SYSTEM_PROMPT)] + history
        else:
            msgs = history
        ai = llm_with_tools.invoke(msgs)
        # Return ONLY the new AI message; add_messages appends it to history
        return {"messages": [ai]}

    # --- Router: do we need to execute tools? ---
    def needs_tools(state: ChatState) -> str:
        last = state["messages"][-1]
        return "tools" if getattr(last, "tool_calls", None) else "end"

    # Build graph
    g = StateGraph(ChatState)
    g.add_node("chatbot", chatbot)
    g.add_node("tools", ToolNode(tools))

    # Edges: chatbot -> (tools | END), tools -> chatbot
    g.add_conditional_edges("chatbot", needs_tools, {"tools": "tools", "end": END})
    g.add_edge("tools", "chatbot")

    # Entry point
    g.set_entry_point("chatbot")

    # Durable checkpoint (sqlite connection, not a string)
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/graph.sqlite", check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return g.compile(checkpointer=checkpointer)

# ============== Adapter so app.py can keep using .run() ==============
class _Adapter:
    def __init__(self, tools):
        self.graph = build_graph(tools)
        self.thread_id = str(uuid.uuid4())

    def run(self, user_text: str) -> str:
        initial = {"messages": [HumanMessage(content=user_text)]}
        out = self.graph.invoke(initial, config={"configurable": {"thread_id": self.thread_id}})
        msgs = out["messages"]
        # Return the last assistant/ai message (handles both lc-core styles)
        for m in reversed(msgs):
            if getattr(m, "role", None) == "assistant" or getattr(m, "type", None) == "ai":
                return m.content
        return "Sorry, I didn't catch that."

def build_agent():
    tools = [create_ticket_tool, get_ticket_status_tool, search_kb_tool, send_confirmation_tool]
    os.makedirs("data", exist_ok=True)
    return _Adapter(tools)

# -------------- optional local CLI --------------
if __name__ == "__main__":
    agent = build_agent()
    print("CityAssist 311 (LangGraph). Type messages, Ctrl+C to exit.")
    while True:
        try:
            text = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break
        if is_emergency(text):
            print("Agent: This sounds like an emergency. Please call 911 immediately.")
            continue
        print("Agent:", agent.run(text))
