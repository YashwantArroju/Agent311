# app.py
import re
import requests
import streamlit as st
from backend.agent import build_agent, is_emergency, run_or_force

# -------------------- Config --------------------
st.set_page_config(page_title="CityAssist 311", page_icon="🏙️", layout="centered")
st.title("CityAssist 311 🏙️")
API_BASE = "http://localhost:8011"  # FastAPI tools server

# -------------------- Session State --------------------
if "agent" not in st.session_state:
    st.session_state.agent = build_agent()

if "history" not in st.session_state:
    # Seed the greeting AS A CHAT MESSAGE so it persists across reruns
    greeting = (
        "Hi! 👋 **Welcome to 311 City Services.** How can I help you today?\n\n"
        "• **Report an issue** (pothole, streetlight out, missed trash…)\n\n"
        "• **Check ticket status** (paste your 8-character ticket ID)\n\n"
        "• **Ask about city services** (missed trash ,noise, potholes, streetlight etc.)\n\n"
    )
    st.session_state.history = [("assistant", greeting)]

# -------------------- Render History --------------------
for role, msg in st.session_state.history:
    with st.chat_message(role):
        st.markdown(msg)

# -------------------- Deterministic fast-path helpers --------------------
EMAIL_RE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"

# Try to spot location in natural text: "at/near/by/on/around <place>"
LOC_HOOK_RE = re.compile(r"(?:\bat\b|\bnear\b|\bby\b|\bon\b|\baround\b)\s+(?P<loc>[^.,;!?]+)", re.IGNORECASE)

# Map common phrases to your categories
CATEGORY_ALIASES = {
    "pothole": ["pothole", "road hole", "street crater"],
    "streetlight": ["streetlight", "street light", "light pole", "lamp post"],
    "missed_trash": ["missed trash", "garbage not collected", "bin still full"],
    "noise": ["noise", "loud party", "construction noise"],
    "bulk_pickup": ["bulk pickup", "sofa", "mattress", "appliance"],
    "graffiti": ["graffiti", "tagging", "spray paint"],
}

def _guess_category(text: str):
    low = (text or "").lower()
    for key, terms in CATEGORY_ALIASES.items():
        if any(t in low for t in terms):
            return key
    return None
#
def _find_labeled(label: str, text: str):
    m = re.search(
        rf"{label}\s*[:\-]\s*(.+?)(?=$|Category:|Description:|Location:|Email:)",
        text, re.I | re.S
    )
    return m.group(1).strip() if m else None

def parse_report(text: str):
    # 1) labels (your existing labeled form)
    cat = _find_labeled("Category", text)
    desc = _find_labeled("Description", text)
    loc = _find_labeled("Location", text)
    email = _find_labeled("Email", text)

    # 2) fallbacks from free text
    if not email:
        m = re.search(EMAIL_RE, text)
        email = m.group(0) if m else None

    if not loc:
        m = LOC_HOOK_RE.search(text)
        if m:
            loc = m.group("loc").strip()

    if not cat:
        cat = _guess_category(text)

    if not desc:
        first = re.split(r"[.!?\n]", text.strip())[0]
        desc = first[:200] if first else None

    return cat, desc, loc, email


def create_ticket_direct(api_base: str, cat: str, desc: str, loc: str, email: str):
    payload = {
        "category": cat,
        "description": desc,
        "address": loc,
        "contact_email": email,
        "contact_phone": ""  # email-only
    }
    r = requests.post(f"{api_base}/create_ticket", json=payload, timeout=10)
    r.raise_for_status()
    return r.json()

# -------------------- Chat Input --------------------
prompt = st.chat_input("Report an issue, check a ticket, or ask about city services…")
if prompt:
    # add user message to history
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.history.append(("user", prompt))

    # emergency guard (no redirects—just a message)
    if is_emergency(prompt):
        reply = "This sounds like an emergency. Please call **911** immediately."
    else:
        # 1) Try deterministic client-side ticket creation (no LLM)
        cat, desc, loc, email = parse_report(prompt)
        if cat and desc and loc and email:
            try:
                data = create_ticket_direct(API_BASE, cat, desc, loc, email)
                reply = (
                    f"Ticket created -  **{data['ticket_id']}**  \n"
                    f"**Category:** {cat}  \n"
                   # f"**Location:** {loc}\n"
                    f"**ETA:** {data.get('eta_days','?')} days" 
                )
            except Exception as e:
                # keep the user on the same page; show the error inline
                reply = f"⚠️ I couldn’t create the ticket right now ({e}). Please try again."
        else:
            # 2) Otherwise let the agent handle status/KB or ask for missing fields
            prev_user = next((m for r, m in reversed(st.session_state.history) if r == "user"), None)
            reply = run_or_force(st.session_state.agent, prompt, prev_user=prev_user, debug=False)

    # add assistant reply to history
    with st.chat_message("assistant"):
        st.markdown(reply)
    st.session_state.history.append(("assistant", reply))
