import streamlit as st
import boto3
import json
import uuid

# --- AWS Bedrock Agent Client ---
client = boto3.client('bedrock-agentcore')

if "user_id" not in st.session_state:
    st.session_state.user_id = str(uuid.uuid4())

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
    
st.set_page_config(page_title="CityAssist Chat", layout="centered")

st.title("💬 CityAssist Chat")

# Initialize chat history with a welcome message
if "messages" not in st.session_state:
    welcome_message = """
    Welcome to CityAssist, Cityville's 311 non-emergency service assistant! I'm here to help you with city-related issues and services.

    How can I assist you today? Would you like to:

    1. Report an issue (like potholes, graffiti, or missed trash collection)
    2. Check the status of an existing ticket
    3. Ask questions about city services
    
    Please let me know what you need help with, and I'll guide you through the process.
    """
    st.session_state.messages = [{"role": "assistant", "content": welcome_message}]


if "messages" not in st.session_state:
    st.session_state.messages = []

# Show previous messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# User input
if prompt := st.chat_input("Enter your question or message:"):
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Display user message
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generate assistant response
    with st.chat_message("assistant"):
        
        # Use the persistent session ID
        agent_runtime_arn = "arn:aws:bedrock-agentcore:us-east-1:356225522107:runtime/agent-nRXAew2YSX"
        
        try:
            placeholder = st.empty()
            streamed_text = ""
            
            agent_response = client.invoke_agent_runtime(
                agentRuntimeArn=agent_runtime_arn,
                runtimeUserId=st.session_state.user_id,
                runtimeSessionId=st.session_state.session_id,
                payload=json.dumps({"prompt": prompt}).encode()
            )
            
            print(f"Response: {agent_response}")
            print(f"Content Type: {agent_response.get("contentType")}")
            
            response = json.loads(agent_response["response"].read().decode("utf-8"))["response"]
            
            st.markdown(response)
            
            st.session_state.messages.append({"role": "assistant", "content": response})
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            