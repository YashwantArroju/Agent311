# CityAssist 311 — Local Development Guide

This README walks you through setting up and running the **CityAssist 311** project locally using a virtual environment, FastAPI for the backend, and Streamlit for the frontend.

> **Tested on:** Windows 10/11 (PowerShell), macOS, and Linux.  
> **Requirements:** Python 3.10+ (3.12 recommended), pip

---

## 1)  redirect to correct root 

```bash
cd Agent311-DatabaseImp
```
## Create a Virtual Environment
```bash
python -m venv .venv
```

## 2) Activate the Virtual Environment

**macOS / Linux (bash/zsh):**
```bash
source .venv/bin/activate
```

**Windows (Command Prompt):**
```bat
.venv\Scripts\activate.bat
```

**Windows (PowerShell):**
```powershell
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, run this **once** in the same terminal:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

After activation, you should see `(.venv)` at the start of your prompt.

---

## 3) Install Dependencies

> Your repository uses a file named **`requirments.txt`** (note the spelling). If your file is named `requirements.txt`, adjust the command accordingly.

```bash
pip install -r requirments.txt
```

---

## 4) Environment Variables (optional but recommended)

Create your local `.env` file from the example and edit if needed.

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**
```bash
cp .env.example .env
```

Common entries for `.env` might include:
```
OPENAI_API_KEY=sk-...
API_BASE=http://127.0.0.1:8001
```

---

## 5) Running the FastAPI Backend

From the **project root**, start the API server:
```bash
uvicorn backend.tools:app --reload --port 8001
```

- FastAPI will start on: **http://127.0.0.1:8001**
- Interactive docs at: **http://127.0.0.1:8001/docs**

---

## 6) Running the Project (Streamlit Frontend)

Open a **new terminal**, activate the **same** virtual environment, then run:
```bash
streamlit run app.py
```

Streamlit will open at: **http://localhost:8501**

---

## 7) (Optional) Quick Backend Test

From the project root (with the venv active):
```bash
python test_ticket.py
```
This sends a sample request to `/create_ticket` and prints the response.

---

## 8) Deactivating the Environment

When you’re finished working on the project, deactivate the virtual environment:
```bash
deactivate
```

---

## Updating a Ticket’s Status (Manual API Call)

You can update a ticket’s status via the backend API. Below are examples in PowerShell and curl.

### Windows PowerShell
```powershell
$body = @{ ticket_id = 'a755841c'; status = 'In Progress' } | ConvertTo-Json
Invoke-RestMethod `
  -Uri http://127.0.0.1:8001/update_ticket_status `
  -Method Post `
  -ContentType 'application/json' `
  -Body $body
```

### macOS / Linux (curl)
```bash
curl -X POST http://127.0.0.1:8001/update_ticket_status \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"a755841c","status":"In Progress"}'
```

> Replace `a755841c` with your actual 8-character `ticket_id` and set `status` to one of your allowed values.

---

## Troubleshooting

- **Activation fails on PowerShell**: Use `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process` once per terminal session.
- **Module not found**: Ensure your venv is activated and dependencies are installed (`pip install -r requirments.txt`).
- **Port already in use**:
  - Backend: change `--port 8001` to another free port and update any clients accordingly.
  - Streamlit: run with `streamlit run app.py --server.port 8502` if 8501 is taken.
- **Cannot reach API from Streamlit**: Confirm the backend is running and `API_BASE` is correct (default: `http://127.0.0.1:8001`).


---

## Notes

- Keep the virtual environment activated in every terminal that interacts with the project.
- If you later add a LangGraph “runtime” service, your Streamlit app can call that service’s `/invoke` endpoint instead of importing the agent locally.
- Commit your `.env.example` (but **not** `.env`) to version control.
