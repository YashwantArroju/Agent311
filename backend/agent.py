# backend/agent.py
# ============================================================
# CityAssist 311 agent — LLM-only (let the model "think" more)
# ============================================================

# --- (optional) silence the LangChain agent deprecation banner ---
import warnings
warnings.filterwarnings(
    "ignore",
    message=r".*LangChain agents will continue to be supported.*"
)

# ===================== Imports =====================
import os
import re
import requests
import yaml
import pathlib
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.agents import initialize_agent, AgentType
from langchain.schema import SystemMessage
from langchain.memory import ConversationBufferMemory
from langchain.prompts import MessagesPlaceholder


# ===================== Env / Config =====================
load_dotenv()
API_BASE = os.getenv("API_BASE", "http://localhost:8011")

# ---------- Load categories from YAML (read once, no code-side classification) ----------
ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root
CATS_PATH = ROOT / "config" / "categories.yaml"
try:
    CATS_YAML_TEXT = CATS_PATH.read_text(encoding="utf-8")
except FileNotFoundError as e:
    raise RuntimeError(
        f"Missing categories file at {CATS_PATH}. "
        "Create config/categories.yaml (see examples we discussed)."
    ) from e

# ===================== Emergency detection =====================
EMERGENCY_REGEX = r"(heart attack|gun|shots fired|fire in (my|the)|unconscious|not breathing|domestic violence|break[- ]?in|armed|stabbed|car crash with injuries)"
def is_emergency(text: str) -> bool:
    return bool(re.search(EMERGENCY_REGEX, text or "", re.IGNORECASE))

# ===================== Tools (FastAPI) =====================
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

@tool
def create_ticket_tool(category: str, description: str, address: str = "", contact_email: str = "") -> str:
    """Create a city service ticket. CALL THIS IMMEDIATELY once you have all four fields:
    category, description, address, contact_email. Do not ask for any other fields. Returns JSON with ticket_id/status/eta_days."""
    
    if not contact_email or not re.search(EMAIL_RE, contact_email):
        return "ERROR: contact_email_missing_or_invalid. Ask for a valid email and call this tool again."

    payload = {
        "category": category,
        "description": description,
        "address": address,
        "contact_email": contact_email,
        #"contact_phone": "",  # email-only
    }
    r = requests.post(f"{API_BASE}/create_ticket", json=payload, timeout=10)
    return r.text

@tool
def get_ticket_status_tool(ticket_id: str) -> str:
    """Get status for an existing ticket_id. Returns JSON."""
    r = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": ticket_id}, timeout=10)
    return r.text

@tool
def search_kb_tool(query: str) -> str:
    """Search city FAQs/KB. Returns answer + source if found."""
    r = requests.post(f"{API_BASE}/search_kb", json={"query": query}, timeout=10)
    return r.text

@tool
def send_confirmation_tool(ticket_id: str) -> str:
    """Send the confirmation email for an existing ticket_id (idempotent; safe to call once)."""
    r = requests.post(f"{API_BASE}/send_confirmation", json={"ticket_id": ticket_id}, timeout=10)
    return r.text

# ===================== System Prompt (includes YAML) =====================
SYSTEM_PROMPT = f"""
You are CityAssist, a generic 311-style non-emergency assistant.

INTENTS → TOOLS
- Report an issue → call create_ticket_tool
- Check ticket status → call get_ticket_status_tool
- Ask about city services → call search_kb_tool

REPORTING
- To create ANY ticket, collect exactly following four fields one at a time.
- First ask for Category,
- Then ask for Description, Description can be ANY description string; do not block on perfect wording.
- Next ask for Location (address or landmark), Location can be ANY location string; do not block on perfect addresses.
- Finally, ask for Contact Email.
- If the user has provided all four, you MUST call create_ticket_tool and send_confirmation_tool.
- After creating a ticket, return ticket_id and ETA.A confirmation email was sent to {{contact_email}}.

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


def build_agent():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [create_ticket_tool, get_ticket_status_tool, search_kb_tool, send_confirmation_tool]
     # 👇 Add conversation memory so the model can collect fields over multiple turns
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )    
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        memory=memory, 
        verbose=False,
        handle_parsing_errors=True,
        agent_kwargs={"system_message": SystemMessage(content=SYSTEM_PROMPT),
                       # <- CRUCIAL: include the conversation in the agent’s prompt
                       "extra_prompt_messages": [MessagesPlaceholder(variable_name="chat_history")],
                       },
    )
    return agent

# ======================================================================
# (NOT NEEDED IN LLM-ONLY MODE)
# ----------------------------------------------------------------------
# The code below was the "fast-path" deterministic helper. It tried to:
# - parse ticket IDs from text and immediately call get_ticket_status_tool
# - extract Category/Description/Location/Email via regex and create a ticket
# You asked to let the LLM do the thinking instead, so this stays commented.
# If you ever want to re-enable it, uncomment and call run_or_force(...) from
# your Streamlit app instead of agent.run(...).
# ======================================================================

"""
# ---------- fast path helpers (deterministic; usually not needed now) ----------
TICKET_ID_RE = r"\\b[a-f0-9]{8}\\b"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}"

def _find_labeled(labels, text: str):
    # supports "Category:", "Description:", "Location:", "Email:"
    import re
    if isinstance(labels, str):
        labels = [labels]
    pat = r"(?:" + "|".join([re.escape(l) for l in labels]) + r")\\s*[:\\-]\\s*(.+?)(?=$|Category:|Description:|Location:|Email:)"
    m = re.search(pat, text or "", re.I | re.S)
    return m.group(1).strip() if m else None

def _extract_report_fields(text: str):
    # NOTE: In the LLM-only flow we don't guess category here; the model does.
    category   = _find_labeled("Category", text)
    description= _find_labeled("Description", text)
    location   = _find_labeled("Location", text)
    email      = _find_labeled("Email", text)

    # validate/extract email anywhere in the text
    candidate = email or (text or "")
    m = re.search(EMAIL_RE, candidate)
    email = m.group(0) if m else None

    # fallback description: first sentence
    if not description:
        s = re.split(r"[.!?\\n]", (text or "").strip())[0]
        description = s[:160] if s else None

    return category, description, location, email

def run_or_force(agent, user_input: str, prev_user: str | None = None, debug: bool = False) -> str:
    # emergency
    if is_emergency(user_input):
        return "This sounds like an emergency. Please call **911** immediately."

    # fast status path
    m = re.search(TICKET_ID_RE, (user_input or "").lower())
    if m:
        tid = m.group(0)
        try:
            r = requests.post(f"{API_BASE}/get_ticket_status", json={"ticket_id": tid}, timeout=10)
            data = r.json()
            if "error" in data:
                return (f"{{'🟡 fast-path(status) — ' if debug else ''}}"
                        f"I couldn't find ticket **{tid}**. Please check the ID or create a new ticket.")
            return (f"{{'🟢 fast-path(status) — ' if debug else ''}}"
                    f"Status for **{{data['ticket_id']}}**: **{{data['status']}}** "
                    f"(dept: {{data.get('dept','N/A')}}, ETA ~ {{data.get('eta_days','?')}} days).")
        except Exception:
            pass

    # extract from current message
    cat, desc, loc, email = _extract_report_fields(user_input)

    # if message is basically "email only", try merging with previous user turn
    if (not (cat and desc and loc) and email and prev_user):
        merged = (prev_user or "") + "\\n" + (user_input or "")
        cat2, desc2, loc2, email2 = _extract_report_fields(merged)
        if cat2 and desc2 and loc2 and email2:
            cat, desc, loc, email = cat2, desc2, loc2, email2

    # create ticket if we have all four pieces
    if cat and desc and loc and email:
        payload = {"category": cat, "description": desc, "address": loc, "contact_email": email}
        try:
            r = requests.post(f"{API_BASE}/create_ticket", json=payload, timeout=10)
            data = r.json()
            if "ticket_id" in data:
                return (f"{{'🟢 fast-path(report) — ' if debug else ''}}"
                        f"Created ticket **{{data['ticket_id']}}** for **{{cat}}** at **{{loc}}**. "
                        f"ETA ~ **{{data['eta_days']}} days**.")
        except Exception:
            pass  # let the agent try

    # otherwise, let the agent drive
    return (f"{{'🌀 agent — ' if debug else ''}}" + agent.run(user_input))
"""

# -------------- local CLI (optional) --------------
if __name__ == "__main__":
    agent = build_agent()
    print("LLM-only CityAssist agent. Type messages, Ctrl+C to exit.")
    while True:
        try:
            text = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break
        if is_emergency(text):
            print("Agent: This sounds like an emergency. Please call 911 immediately.")
            continue
        print("Agent:", agent.run(text))
