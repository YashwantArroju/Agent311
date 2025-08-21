# backend/agent.py

# --- (optional) silence the LangChain agent deprecation banner ---
import warnings
warnings.filterwarnings(
    "ignore",
    message=r".*LangChain agents will continue to be supported.*"
)

# ===================== Imports =====================
import os, re, requests, yaml, pathlib
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.tools import tool
from langchain.agents import initialize_agent, AgentType
from langchain.schema import SystemMessage

# ===================== Env / Config =====================
load_dotenv()
API_BASE = os.getenv("API_BASE", "http://localhost:8011")

# ---------- Load categories from YAML (no hard-coded fallback) ----------
ROOT = pathlib.Path(__file__).resolve().parents[1]  # project root
CATS_PATH = ROOT / "config" / "categories.yaml"

with open(CATS_PATH, "r", encoding="utf-8") as f:
    _raw = yaml.safe_load(f) or []

# Normalize YAML rows -> CATEGORIES: [{key, detect, required_fields}]
CATEGORIES = []
for row in _raw:
    key = row.get("key")
    if not key:
        continue
    detect = row.get("detect") or row.get("examples") or []
    detect = [t for t in detect if isinstance(t, str) and t.strip()]
    req = row.get("required_fields") or row.get("required") or []
    CATEGORIES.append({"key": key, "detect": detect, "required_fields": req})

if not CATEGORIES:
    # Force YAML presence since we removed hard-coded categories
    raise RuntimeError("config/categories.yaml is missing or empty.")

# ---------- Build alias map and boundary-aware patterns from YAML ----------
CATEGORY_ALIASES = {row["key"]: list(dict.fromkeys(row.get("detect", []))) for row in CATEGORIES}

def _compile_patterns(aliases: dict[str, list[str]]):
    compiled: dict[str, list[re.Pattern]] = {}
    for key, terms in aliases.items():
        pats = []
        for t in terms:
            if t:
                # word-boundary, case-insensitive; escape special chars
                pats.append(re.compile(rf"\b{re.escape(t.lower())}\b", re.IGNORECASE))
        compiled[key] = pats
    return compiled

TERM_PATTERNS = _compile_patterns(CATEGORY_ALIASES)

def _guess_category(text: str) -> str | None:
    """
    YAML-driven category guess (prefers the longest matching term).
    """
    low = (text or "").lower()
    best_key, best_len = None, 0
    for key, patterns in TERM_PATTERNS.items():
        for p in patterns:
            m = p.search(low)
            if m:
                L = len(m.group(0))
                if L > best_len:
                    best_key, best_len = key, L
    return best_key

# ===================== Emergency detection =====================
EMERGENCY_REGEX = r"(heart attack|gun|shots fired|fire in (my|the)|unconscious|not breathing|domestic violence|break[- ]?in|armed|stabbed|car crash with injuries)"
def is_emergency(text: str) -> bool:
    return bool(re.search(EMERGENCY_REGEX, text or "", re.IGNORECASE))

# ===================== Tools (FastAPI) =====================
@tool
def create_ticket_tool(category: str, description: str, address: str = "", contact_email: str = "") -> str:
    """Create a city service ticket. Return JSON with ticket_id/status/eta_days."""
    payload = {
        "category": category,
        "description": description,
        "address": address,
        "contact_email": contact_email,
        "contact_phone": "",  # email-only
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

# ===================== System Prompt =====================
SYSTEM_PROMPT = """
You are CityAssist, a generic 311-style non-emergency assistant.

INTENTS → TOOLS
- Report an issue → call create_ticket_tool
- Check ticket status → call get_ticket_status_tool
- Ask about city services → call search_kb_tool

REPORTING (EMAIL ONLY)
- Required to create a ticket: Category, Description, Location (address or landmark), and Contact Email.
- Location can be ANY location string; do not block on perfect addresses.
- If the user has provided all four, you MUST call create_ticket_tool. Do not ask for a phone number.
- If something is missing, ask ONLY for the missing pieces in one brief question (prioritize asking for the email if it's missing).
- After creating a ticket, return ticket_id and ETA.

STATUS
- If a ticket ID (8 characters) is present, call get_ticket_status_tool and summarize status/ETA/department.
- Otherwise, ask briefly for the ticket ID.

KB
- For service questions (missed trash, pothole, streetlight, noise etc.), call search_kb_tool.
- If no answer is found, say so and offer to create a ticket.

GUARDRAILS
- If the message suggests an emergency, say: "Call 911 now." Do not call any tools.
- Be concise, friendly, and action-oriented. Never ask for a phone number.
"""

def build_agent():
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    tools = [create_ticket_tool, get_ticket_status_tool, search_kb_tool]
    agent = initialize_agent(
        tools,
        llm,
        agent=AgentType.OPENAI_FUNCTIONS,
        verbose=False,
        handle_parsing_errors=True,
        agent_kwargs={"system_message": SystemMessage(content=SYSTEM_PROMPT)},
    )
    return agent

# ===================== Fast-path helpers (unchanged) =====================
TICKET_ID_RE = r"\b[a-f0-9]{8}\b"
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

def _find_labeled(labels, text: str):
    # supports "Category:", "Description:", "Location:", "Contact:", "Email:"
    if isinstance(labels, str):
        labels = [labels]
    pat = r"(?:" + "|".join([re.escape(l) for l in labels]) + r")\s*[:\-]\s*(.+?)(?=$|Category:|Description:|Location:|Contact:|Email:)"
    m = re.search(pat, text or "", re.I | re.S)
    return m.group(1).strip() if m else None

def _extract_report_fields(text: str):
    # Use label if present, otherwise YAML-based guesser
    category = _find_labeled("Category", text) or _guess_category(text)
    description = _find_labeled("Description", text)
    location   = _find_labeled("Location", text)
    email      = _find_labeled("Email", text)

    # validate/extract email anywhere in the text
    candidate = email or (text or "")
    m = re.search(EMAIL_RE, candidate)
    email = m.group(0) if m else None

    # fallback description: first sentence
    if not description:
        s = re.split(r"[.!?\n]", (text or "").strip())[0]
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
                return (f"{'🟡 fast-path(status) — ' if debug else ''}"
                        f"I couldn't find ticket **{tid}**. Please check the ID or create a new ticket.")
            return (f"{'🟢 fast-path(status) — ' if debug else ''}"
                    f"Status for **{data['ticket_id']}**: **{data['status']}** "
                    f"(dept: {data.get('dept','N/A')}, ETA ~ {data.get('eta_days','?')} days).")
        except Exception:
            pass

    # extract from current message
    cat, desc, loc, email = _extract_report_fields(user_input)

    # if message is basically "email only", try merging with previous user turn
    if (not (cat and desc and loc) and email and prev_user):
        merged = (prev_user or "") + "\n" + (user_input or "")
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
                return (f"{'🟢 fast-path(report) — ' if debug else ''}"
                        f"Created ticket **{data['ticket_id']}** for **{cat}** at **{loc}**. "
                        f"ETA ~ **{data['eta_days']} days**.")
        except Exception:
            pass  # let the agent try

    # otherwise, let the agent drive
    return (f"{'🌀 agent — ' if debug else ''}" + agent.run(user_input))

# optional local CLI
if __name__ == "__main__":
    agent = build_agent()
    while True:
        text = input("User: ")
        print(run_or_force(agent, text))
