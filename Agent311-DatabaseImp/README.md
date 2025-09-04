# Agent311 — Local Setup Guide

Follow the steps below to set up and run the project on your local machine.

---

## 1. Create a Virtual Environment

From the **root directory** of the project, run:

```bash
python -m venv .venv

## 2. Activate the Virtual Environment

macOS / Linux (bash/zsh):

source .venv/bin/activate


Windows (Command Prompt):

.venv\Scripts\activate.bat


Windows (PowerShell):

.\.venv\Scripts\Activate.ps1


If PowerShell blocks activation, run this once in the same terminal:

Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process


After activation, you should see (.venv) at the start of your prompt.

### 3. Install Dependencies


pip install -r requirments.txt

### 4. Environment Variables (optional but recommended)

Create your local .env file from the example and edit if needed.

Windows (PowerShell):

Copy-Item .env.example .env

macOS / Linux:

cp .env.example .env

## 5. Running the FastAPI Backend

From the project root, start the API server:

uvicorn backend.tools:app --reload --port 8001

##6. Running the Project (Streamlit Frontend)

Open a new terminal, activate the same virtual environment, then run:

streamlit run app.py


Streamlit will open at:
http://localhost:8501

## 7. (Optional) Quick Backend Test

From the project root (with the venv active):

python test_ticket.py


This sends a sample request to /create_ticket and prints the response.

## 8.Deactivating the Environment

When you’re finished working on the project, deactivate the virtual environment:

deactivate

to update the status of the ticket :

''bash 
$body = @{ ticket_id = 'a755841c'; status = 'In Progress' } | ConvertTo-Json
Invoke-RestMethod -Uri http://localhost:8001/update_ticket_status -Method Post -ContentType 'application/json' -Body $body
'''