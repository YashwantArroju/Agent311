# # # # backend/agent.py
# # # # ============================================================
# # # # CityAssist 311 agent — LLM-only (let the model "think" more)
# # # # ============================================================

# # # # --- (optional) silence the LangChain agent deprecation banner ---
# # # import warnings
# # # warnings.filterwarnings(
# # #     "ignore",
# # #     message=r".*LangChain agents will continue to be supported.*"
# # # )

# # # # ===================== Imports =====================
# # # import os
# # # import re
# # # import requests
# # # import yaml
# # # import pathlib
# # # from dotenv import load_dotenv

# # # from langchain_openai import ChatOpenAI
# # # from langchain.tools import tool
# # # from langchain.agents import initialize_agent, AgentType
# # # from langchain.schema import SystemMessage
# # # from langchain.memory import ConversationBufferMemory
# # # from langchain.prompts import MessagesPlaceholder


# # # # ===================== Env / Config =====================
# # # load_dotenv()
# # # API_BASE = os.getenv("API_BASE", "http://localhost:8001")

# # # # ---------- Load categories from YAML (read once, no code-side classification) ----------
# # # ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root
# # # CATS_PATH = ROOT / "config" / "categories.yaml"
# # # try:
# # #     CATS_YAML_TEXT = CATS_PATH.read_text(encoding="utf-8")
# # # except FileNotFoundError as e:
# # #     raise RuntimeError(
# # #         f"Missing categories file at {CATS_PATH}. "
# # #         "Create config/categories.yaml (see examples we discussed)."
# # #     ) from e

# # # # ===================== Emergency detection =====================
# # # EMERGENCY_REGEX = r"(heart attack|gun|shots fired|fire in (my|the)|unconscious|not breathing|domestic violence|break[- ]?in|armed|stabbed|car crash with injuries)"
# # # def is_emergency(text: str) -> bool:
# # #     return bool(re.search(EMERGENCY_REGEX, text or "", re.IGNORECASE))

# # # # ===================== Tools (FastAPI) =====================
# # # EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# # # @tool
# # # def create_ticket_tool(category: str, description: str, address: str = "", contact_email: str = "") -> str:
# # #     """Create a city service ticket. CALL THIS IMMEDIATELY once you have all four fields:
# # #     category, description, address, contact_email. Do not ask for any other fields. Returns JSON with ticket_id/status/eta_days."""
    
# # #     if not contact_email or not re.search(EMAIL_RE, contact_email):
# # #         return "ERROR: contact_email_missing_or_invalid. Ask for a valid email and call this tool again."

# # #     payload = {
# # #         "category": category,
# # #         "description": description,
# # #         "address": address,
# # #         "contact_email": contact_email,
# # #         #"contact_phone": "",  # email-only
# # #     }
# # #     r = requests.post(f"{API_BASE}/create_ticket", json=payload, timeout=10)
# # #     return r.text

# # # @tool
# # # def get_ticket_status_tool(ticket_id: str) -> str:
# # #     """Get status for an existing ticket_id. Returns JSON."""
# # #     r = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": ticket_id}, timeout=10)
# # #     return r.text

# # # @tool
# # # def search_kb_tool(query: str) -> str:
# # #     """Search city FAQs/KB. Returns answer + source if found."""
# # #     r = requests.post(f"{API_BASE}/search_kb", json={"query": query}, timeout=10)
# # #     return r.text

# # # @tool
# # # def send_confirmation_tool(ticket_id: str) -> str:
# # #     """Send the confirmation email for an existing ticket_id (idempotent; safe to call once)."""
# # #     r = requests.post(f"{API_BASE}/send_confirmation", json={"ticket_id": ticket_id}, timeout=10)
# # #     return r.text

# # # # ===================== System Prompt (includes YAML) =====================
# # # SYSTEM_PROMPT = f"""
# # # You are CityAssist, a generic 311-style non-emergency assistant.

# # # INTENTS → TOOLS
# # # - Report an issue → call create_ticket_tool
# # # - Check ticket status → call get_ticket_status_tool
# # # - Ask about city services → call search_kb_tool

# # # REPORTING
# # # - To create ANY ticket, collect exactly following four fields one at a time.
# # # - First ask for Category,
# # # - Then ask for Description, Description can be ANY description string; do not block on perfect wording.
# # # - Next ask for Location (address or landmark), Location can be ANY location string; do not block on perfect addresses.
# # # - Finally, ask for Contact Email.
# # # - If the user has provided all four, you MUST call create_ticket_tool and send_confirmation_tool.
# # # - After creating a ticket, return ticket_id and ETA.A confirmation email was sent to {{contact_email}}.

# # # STATUS
# # # - If a ticket ID (8 characters) is present, call get_ticket_status_tool and summarize status/ETA/department.
# # # - Otherwise, ask briefly for the ticket ID.

# # # KB
# # # - For service questions (missed trash, pothole, streetlight, noise etc.), you MUST call search_kb_tool with the user’s exact text. Do NOT answer from your own knowledge.
# # # - Give a concise, general answer. Then IMMEDIATELY offer to create a ticket.
# # # - If the user agrees (e.g., “yes”, “please do”, “create it”), PROCEED to collect ONLY the four fields and CALL create_ticket_tool. Do NOT re-ask already provided info. Do NOT loop.

# # # GUARDRAILS
# # # - If the message suggests an emergency, say: "Call 911 now." Do not call any tools.
# # # - Be concise, friendly, and action-oriented. Never ask for a phone number.
# # # - Avoid repeating the same follow-up question more than once. If the user doesn’t provide a missing field after one ask, explain why it’s needed and stop.
# # # - Do not invent data. If a required field is missing, ask for it directly.

# # # You have access to the city's service taxonomy below. Use it to classify user requests and to know which fields to collect.

# # # CATEGORIES_YAML:
# # # ---
# # # {CATS_YAML_TEXT}
# # # ---
# # # """


# # # def build_agent():
# # #     llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
# # #     tools = [create_ticket_tool, get_ticket_status_tool, search_kb_tool, send_confirmation_tool]
# # #      # 👇 Add conversation memory so the model can collect fields over multiple turns
# # #     memory = ConversationBufferMemory(
# # #         memory_key="chat_history",
# # #         return_messages=True,
# # #     )    
# # #     agent = initialize_agent(
# # #         tools,
# # #         llm,
# # #         agent=AgentType.OPENAI_FUNCTIONS,
# # #         memory=memory, 
# # #         verbose=False,
# # #         handle_parsing_errors=True,
# # #         agent_kwargs={"system_message": SystemMessage(content=SYSTEM_PROMPT),
# # #                        # <- CRUCIAL: include the conversation in the agent’s prompt
# # #                        "extra_prompt_messages": [MessagesPlaceholder(variable_name="chat_history")],
# # #                        },
# # #     )
# # #     return agent

# # # # ======================================================================
# # # # (NOT NEEDED IN LLM-ONLY MODE)
# # # # ----------------------------------------------------------------------
# # # # The code below was the "fast-path" deterministic helper. It tried to:
# # # # - parse ticket IDs from text and immediately call get_ticket_status_tool
# # # # - extract Category/Description/Location/Email via regex and create a ticket
# # # # You asked to let the LLM do the thinking instead, so this stays commented.
# # # # If you ever want to re-enable it, uncomment and call run_or_force(...) from
# # # # your Streamlit app instead of agent.run(...).
# # # # ======================================================================

# # # """
# # # # ---------- fast path helpers (deterministic; usually not needed now) ----------
# # # TICKET_ID_RE = r"\\b[a-f0-9]{8}\\b"
# # # EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"

# # # def _find_labeled(labels, text: str):
# # #     # supports "Category:", "Description:", "Location:", "Email:"
# # #     import re
# # #     if isinstance(labels, str):
# # #         labels = [labels]
# # #     pat = r"(?:" + "|".join([re.escape(l) for l in labels]) + r")\\s*[:\\-]\\s*(.+?)(?=$|Category:|Description:|Location:|Email:)"
# # #     m = re.search(pat, text or "", re.I | re.S)
# # #     return m.group(1).strip() if m else None

# # # def _extract_report_fields(text: str):
# # #     # NOTE: In the LLM-only flow we don't guess category here; the model does.
# # #     category   = _find_labeled("Category", text)
# # #     description= _find_labeled("Description", text)
# # #     location   = _find_labeled("Location", text)
# # #     email      = _find_labeled("Email", text)

# # #     # validate/extract email anywhere in the text
# # #     candidate = email or (text or "")
# # #     m = re.search(EMAIL_RE, candidate)
# # #     email = m.group(0) if m else None

# # #     # fallback description: first sentence
# # #     if not description:
# # #         s = re.split(r"[.!?\\n]", (text or "").strip())[0]
# # #         description = s[:160] if s else None

# # #     return category, description, location, email

# # # def run_or_force(agent, user_input: str, prev_user: str | None = None, debug: bool = False) -> str:
# # #     # emergency
# # #     if is_emergency(user_input):
# # #         return "This sounds like an emergency. Please call **911** immediately."

# # #     # fast status path
# # #     m = re.search(TICKET_ID_RE, (user_input or "").lower())
# # #     if m:
# # #         tid = m.group(0)
# # #         try:
# # #             r = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": tid}, timeout=10)
# # #             data = r.json()
# # #             if "error" in data:
# # #                 return (f"{{'🟡 fast-path(status) — ' if debug else ''}}"
# # #                         f"I couldn't find ticket **{tid}**. Please check the ID or create a new ticket.")
# # #             return (f"{{'🟢 fast-path(status) — ' if debug else ''}}"
# # #                     f"Status for **{{data['ticket_id']}}**: **{{data['status']}}** "
# # #                     f"(dept: {{data.get('dept','N/A')}}, ETA ~ {{data.get('eta_days','?')}} days).")
# # #         except Exception:
# # #             pass

# # #     # extract from current message
# # #     cat, desc, loc, email = _extract_report_fields(user_input)

# # #     # if message is basically "email only", try merging with previous user turn
# # #     if (not (cat and desc and loc) and email and prev_user):
# # #         merged = (prev_user or "") + "\\n" + (user_input or "")
# # #         cat2, desc2, loc2, email2 = _extract_report_fields(merged)
# # #         if cat2 and desc2 and loc2 and email2:
# # #             cat, desc, loc, email = cat2, desc2, loc2, email2

# # #     # create ticket if we have all four pieces
# # #     if cat and desc and loc and email:
# # #         payload = {"category": cat, "description": desc, "address": loc, "contact_email": email}
# # #         try:
# # #             r = requests.post(f"{API_BASE}/create_ticket", json=payload, timeout=10)
# # #             data = r.json()
# # #             if "ticket_id" in data:
# # #                 return (f"{{'🟢 fast-path(report) — ' if debug else ''}}"
# # #                         f"Created ticket **{{data['ticket_id']}}** for **{{cat}}** at **{{loc}}**. "
# # #                         f"ETA ~ **{{data['eta_days']}} days**.")
# # #         except Exception:
# # #             pass  # let the agent try

# # #     # otherwise, let the agent drive
# # #     return (f"{{'🌀 agent — ' if debug else ''}}" + agent.run(user_input))
# # # """

# # # # -------------- local CLI (optional) --------------
# # # if __name__ == "__main__":
# # #     agent = build_agent()
# # #     print("LLM-only CityAssist agent. Type messages, Ctrl+C to exit.")
# # #     while True:
# # #         try:
# # #             text = input("You: ")
# # #         except (EOFError, KeyboardInterrupt):
# # #             break
# # #         if is_emergency(text):
# # #             print("Agent: This sounds like an emergency. Please call 911 immediately.")
# # #             continue
# # #         print("Agent:", agent.run(text))
# # # backend/agent.py
# # # ============================================================
# # # CityAssist 311 agent — LangGraph prebuilt ReAct (LLM-only)
# # # Keeps the same functionality and .run() interface as before
# # # ============================================================



# import warnings
# warnings.filterwarnings("ignore", message=r".*LangChain agents will continue to be supported.*")

# # ---------- std imports ----------
# import os
# import re
# import uuid
# import json
# import pathlib
# import sqlite3
# import requests
# from dotenv import load_dotenv

# # ---------- langchain / llm ----------
# from langchain_openai import ChatOpenAI
# from langchain.tools import tool
# from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

# # ---------- langgraph ----------
# from langgraph.graph import StateGraph, END
# from langgraph.prebuilt import ToolNode             # executes @tool functions
# from langgraph.checkpoint.sqlite import SqliteSaver # durable state (survives reloads)
# from langgraph.graph.message import add_messages

# # ============== Env / Config ==============
# load_dotenv()
# API_BASE = os.getenv("API_BASE", "http://localhost:8001")

# # Load categories YAML once (we just embed the raw text in the prompt)
# ROOT = pathlib.Path(__file__).resolve().parents[1]
# CATS_PATH = ROOT / "config" / "categories.yaml"
# try:
#     CATS_YAML_TEXT = CATS_PATH.read_text(encoding="utf-8")
# except FileNotFoundError as e:
#     raise RuntimeError(
#         f"Missing categories file at {CATS_PATH}. "
#         "Create config/categories.yaml."
#     ) from e

# # ============== Emergency detection ==============
# EMERGENCY_REGEX = r"(heart attack|gun|shots fired|fire in (my|the)|unconscious|not breathing|domestic violence|break[- ]?in|armed|stabbed|car crash with injuries)"
# def is_emergency(text: str) -> bool:
#     return bool(re.search(EMERGENCY_REGEX, text or "", re.IGNORECASE))

# # ============== Tools (create auto-sends confirmation) ==============
# EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# @tool
# def create_ticket_tool(category: str, description: str, address: str = "", contact_email: str = "") -> str:
#     """Create a city service ticket once you have: category, description, address, contact_email.
#     Returns JSON with ticket_id/status/eta_days. Also auto-sends the confirmation email."""
#     if not contact_email or not re.search(EMAIL_RE, contact_email):
#         return "ERROR: contact_email_missing_or_invalid. Ask for a valid email and call this tool again."

#     payload = {"category": category, "description": description, "address": address, "contact_email": contact_email}
#     r = requests.post(f"{API_BASE}/create_ticket", json=payload, timeout=10)
#     text = r.text

#     # Try to auto-send confirmation if we got a ticket_id back
#     try:
#         data = r.json()
#     except Exception:
#         data = None

#     if isinstance(data, dict) and "ticket_id" in data:
#         try:
#             # idempotent; safe to call
#             requests.post(
#                 f"{API_BASE}/send_confirmation",
#                 json={"ticket_id": data["ticket_id"]},
#                 timeout=10
#             )
#             data["confirmation_email_sent"] = True
#             return json.dumps(data)
#         except Exception:
#             # if email send fails, still return the create response
#             pass

#     return text

# @tool
# def get_ticket_status_tool(ticket_id: str) -> str:
#     """Get status for an existing ticket_id. Returns JSON."""
#     r = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": ticket_id}, timeout=10)
#     return r.text

# @tool
# def search_kb_tool(query: str) -> str:
#     """Search city FAQs/KB. Returns answer + source if found."""
#     r = requests.post(f"{API_BASE}/search_kb", json={"query": query}, timeout=10)
#     return r.text

# @tool
# def send_confirmation_tool(ticket_id: str) -> str:
#     """Resend the confirmation email for an existing ticket_id (idempotent)."""
#     r = requests.post(f"{API_BASE}/send_confirmation", json={"ticket_id": ticket_id}, timeout=10)
#     return r.text

# # ============== System prompt (updated to reflect auto-send) ==============
# SYSTEM_PROMPT = f"""
# You are CityAssist, a generic 311-style non-emergency assistant.

# INTENTS → TOOLS
# - Report an issue → call create_ticket_tool
# - Check ticket status → call get_ticket_status_tool
# - Ask about city services → call search_kb_tool

# REPORTING
# - To create ANY ticket, collect exactly the following four fields one at a time:
#   1) Category, 2) Description, 3) Location (address or landmark), 4) Contact Email.
# - If the user has provided all four, you MUST call create_ticket_tool immediately.
# - NOTE: create_ticket_tool automatically sends the confirmation email. You do NOT need to call send_confirmation_tool after creation.
#   Only call send_confirmation_tool if the user asks to resend or says they didn’t receive it.
# - After creating a ticket, return ticket_id and ETA. Say that a confirmation email was sent to {{contact_email}}.

# STATUS
# - If a ticket ID (8 characters) is present, call get_ticket_status_tool and summarize status/ETA/department.
# - Otherwise, ask briefly for the ticket ID.

# KB
# - For service questions (missed trash, pothole, streetlight, noise etc.), you MUST call search_kb_tool with the user’s exact text. Do NOT answer from your own knowledge.
# - Give a concise, general answer. Then IMMEDIATELY offer to create a ticket.
# - If the user agrees (e.g., “yes”, “please do”, “create it”), PROCEED to collect ONLY the four fields and CALL create_ticket_tool. Do NOT re-ask already provided info. Do NOT loop.

# GUARDRAILS
# - If the message suggests an emergency, say: "Call 911 now." Do not call any tools.
# - Be concise, friendly, and action-oriented. Never ask for a phone number.
# - Avoid repeating the same follow-up question more than once. If the user doesn’t provide a missing field after one ask, explain why it’s needed and stop.
# - Do not invent data. If a required field is missing, ask for it directly.

# You have access to the city's service taxonomy below. Use it to classify user requests and to know which fields to collect.

# CATEGORIES_YAML:
# ---
# {CATS_YAML_TEXT}
# ---
# """

# # ============== LangGraph state ==============
# from typing import TypedDict, List, Annotated
# class ChatState(TypedDict):
#     # Crucial: use add_messages so nodes append to history (LLM replies, ToolNode outputs, etc.)
#     messages: Annotated[List[BaseMessage], add_messages]

# # ============== Build the manual graph ==============
# def build_graph(tools):
#     # LLM bound to tools
#     llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
#     llm_with_tools = llm.bind_tools(tools)

#     # --- Node: chatbot (calls the model) ---
#     def chatbot(state: ChatState):
#         history = state["messages"]
#         # Prepend system message for the *call*, but don't store it in state
#         if not history or not isinstance(history[0], SystemMessage):
#             msgs = [SystemMessage(content=SYSTEM_PROMPT)] + history
#         else:
#             msgs = history
#         ai = llm_with_tools.invoke(msgs)
#         # Return ONLY the new AI message; add_messages appends it to history
#         return {"messages": [ai]}

#     # --- Router: do we need to execute tools? ---
#     def needs_tools(state: ChatState) -> str:
#         last = state["messages"][-1]
#         return "tools" if getattr(last, "tool_calls", None) else "end"

#     # Build graph
#     g = StateGraph(ChatState)
#     g.add_node("chatbot", chatbot)
#     g.add_node("tools", ToolNode(tools))

#     # Edges: chatbot -> (tools | END), tools -> chatbot
#     g.add_conditional_edges("chatbot", needs_tools, {"tools": "tools", "end": END})
#     g.add_edge("tools", "chatbot")

#     # Entry point
#     g.set_entry_point("chatbot")

#     # Durable checkpoint (sqlite connection, not a string)
#     os.makedirs("data", exist_ok=True)
#     conn = sqlite3.connect("data/graph.sqlite", check_same_thread=False)
#     checkpointer = SqliteSaver(conn)

#     return g.compile(checkpointer=checkpointer)

# # ============== Adapter so app.py can keep using .run() ==============
# class _Adapter:
#     def __init__(self, tools):
#         self.graph = build_graph(tools)
#         self.thread_id = str(uuid.uuid4())

#     def run(self, user_text: str) -> str:
#         initial = {"messages": [HumanMessage(content=user_text)]}
#         out = self.graph.invoke(initial, config={"configurable": {"thread_id": self.thread_id}})
#         msgs = out["messages"]
#         # Return the last assistant/ai message (handles both lc-core styles)
#         for m in reversed(msgs):
#             if getattr(m, "role", None) == "assistant" or getattr(m, "type", None) == "ai":
#                 return m.content
#         return "Sorry, I didn't catch that."

# def build_agent():
#     tools = [create_ticket_tool, get_ticket_status_tool, search_kb_tool, send_confirmation_tool]
#     os.makedirs("data", exist_ok=True)
#     return _Adapter(tools)

# # -------------- optional local CLI --------------
# if __name__ == "__main__":
#     agent = build_agent()
#     print("CityAssist 311 (LangGraph). Type messages, Ctrl+C to exit.")
#     while True:
#         try:
#             text = input("You: ")
#         except (EOFError, KeyboardInterrupt):
#             break
#         if is_emergency(text):
#             print("Agent: This sounds like an emergency. Please call 911 immediately.")
#             continue
#         print("Agent:", agent.run(text))
# backend/agent.py
# ============================================================
# CityAssist 311 agent — Manual LangGraph (custom StateGraph)
# Uses Gmail service-account tool for confirmations (no FastAPI)
# Works with Streamlit via build_agent() and .run(user_text)
# ============================================================

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
