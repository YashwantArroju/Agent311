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

# --- Streamlit UI ---
st.set_page_config(page_title="Bedrock Agent Chat", layout="centered")

st.title("💬 AWS Bedrock Agent Chat")

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
            
            response = agent_response["response"].read().decode("utf-8")
            
            st.markdown(response)
            
        #### Ignore this part, was trying to stream the response
            
            # for line in agent_response["response"].iter_lines():
            #     if not line:
            #         continue
                    
            #     line = line.decode("utf-8")
                
            #     # print(f"line: {line}") # This will print to the terminal
            #     st.write(line) # This will display in the Streamlit app
                    
            #     streamed_text += line
            #     # placeholder.markdown(streamed_text + "▌")  # cursor effect

            
            # Remove cursor and finalize response
            # placeholder.markdown(streamed_text)
        
        ####
            
            # Add assistant response to chat history
            st.session_state.messages.append({"role": "assistant", "content": response})
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
            