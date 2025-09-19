# rag_query_lambda.py
import json
import os
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1")
OPENSEARCH_HOST = os.environ.get("OPENSEARCH_HOST", "266mw10z7j81zyo2a6a8.us-east-1.aoss.amazonaws.com")
INDEX_NAME = os.environ.get("INDEX_NAME", "cityassist_rag")
DEFAULT_TOP_K = int(os.environ.get("TOP_K", "5"))

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

def get_os_client():
    session = boto3.Session()
    credentials = session.get_credentials()
    auth = AWSV4SignerAuth(credentials, "us-east-1", "aoss")
    return OpenSearch(
        hosts=[{"host": OPENSEARCH_HOST, "port": 443}],
        use_ssl=True,
        verify_certs=True,
        http_auth=auth,
        connection_class=RequestsHttpConnection,
        timeout=30,
        max_retries=3,
        retry_on_timeout=True,
    )

def embed_query(q: str):
    resp = bedrock.invoke_model(
        modelId=EMBEDDING_MODEL_ID,
        body=json.dumps({"inputText": q}),
        contentType="application/json",
        accept="application/json"
    )
    body = json.loads(resp["body"].read())
    return body["embedding"]

# def vector_search(client, query_vec, top_k):
def vector_search(client, query_vec, top_k, similarity_threshold=0.65):
    # OpenSearch k-NN vector query
    body = {
        "size": top_k,
        "min_score": similarity_threshold,
        "query": {
            "knn": {
                "embedding": {
                    "vector": query_vec,
                    "k": top_k
                }
            }
        },
        "_source": ["text", "source", "page", "category"]
    }
    res = client.search(index=INDEX_NAME, body=body)
    hits = res.get("hits", {}).get("hits", [])
    results = []
    for h in hits:
        src = h.get("_source", {})
        score = h.get("_score", 0.0)
        results.append({
            "text": src.get("text", ""),
            "source": src.get("source"),
            "page": src.get("page"),
            "category": src.get("category"),
            "score": score
        })
    return results

def handler(event, context):
    """
    Request contract (what your AgentCore tool will send):
      {
        "query": "When is bulky trash collected?",
        "top_k": 5   # optional
      }

    Response (what the agent will get back and feed to Claude):
      {
        "results": [
           {"text": "...", "source": "...", "page": 12, "category":"sanitation", "score": 1.23},
           ...
        ]
      }
    """
    try:
        if isinstance(event, str):
            event = json.loads(event)

        query = event.get("query") or event.get("input") or event.get("q")
        if not query:
            return {"statusCode": 400, "body": json.dumps({"error": "Missing 'query'"})}

        top_k = int(event.get("top_k", DEFAULT_TOP_K))

        client = get_os_client()
        qvec = embed_query(query)
        # results = vector_search(client, qvec, top_k)
        results = vector_search(client, qvec, top_k, 0.65)

        print("query: ", query)
        print("results: ", results)


        return {
            "statusCode": 200,
            "body": json.dumps({"results": results})
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
        
        