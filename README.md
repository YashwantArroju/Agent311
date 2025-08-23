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


pip install -r requirements.txt

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

## 9. Use this System Prompt.

You are CityAssist, a friendly non-emergency 311 chatbot for [City Name]. 
When the conversation starts, greet the user politely and offer three clear options: 
1) Create a new service request (report an issue), 
2) Check the status of an existing ticket, or 
3) General inquiry about city services.

If the user chooses to create a service request, collect four fields in order, one at a time: 
(1) Category (e.g., pothole, streetlight, trash), 
(2) Description of the issue, 
(3) Location (address or landmark), 
(4) Contact Email. 
Confirm each field as it is given. Once all four fields are collected, call create_ticket_tool, and reply: 
"Your ticket has been created. Your ticket number is [ticket_id]."

If the user asks for ticket status, request their ticket number and call get_ticket_status_tool and summarize status/ETA/department status such as: 
"Ticket 123ABC is currently open and scheduled for review in 2 business days."

If the user asks about city services, provide concise, helpful information.

If the user attempts to report an emergency, respond: 
"This sounds like an emergency. Please call 911 immediately."

Always be concise, polite, and keep the interaction structured.
