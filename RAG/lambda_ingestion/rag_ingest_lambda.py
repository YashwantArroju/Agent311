
# rag_ingest_lambda.py
import json
import os
import io
import math
import boto3
from pypdf import PdfReader
from opensearchpy import OpenSearch, RequestsHttpConnection, AWSV4SignerAuth

EMBEDDING_MODEL_ID = os.environ.get("EMBEDDING_MODEL_ID", "amazon.titan-embed-text-v1")
OPENSEARCH_HOST = os.environ["OPENSEARCH_HOST"]        # e.g., abcd12345.us-east-1.aoss.amazonaws.com
INDEX_NAME = os.environ.get("INDEX_NAME", "cityassist_rag")

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

# --- OpenSearch client with SigV4 ---
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

# --- Ensure index exists with correct mapping ---
def ensure_index(client, dim):
    if client.indices.exists(index=INDEX_NAME):
        return
    body = {
        "settings": {
            "index": {
                "knn": True
            }
        },
        "mappings": {
            "properties": {
                "text": {"type": "text"},
                "source": {"type": "keyword"},
                "page": {"type": "integer"},
                "category": {"type": "keyword"},
                "embedding": {
                    "type": "knn_vector",
                    "dimension": dim,
                    "method": {
                        "name": "hnsw",
                        "space_type": "cosinesimil",
                        "engine": "faiss"
                    }
                }
            }
        }
    }
    client.indices.create(index=INDEX_NAME, body=body)

# --- Call Bedrock embeddings (Titan text) ---
def embed_texts(texts):
    # Titan supports batching; we’ll do simple per-text calls for clarity.
    vectors = []
    for t in texts:
        resp = bedrock.invoke_model(
            modelId=EMBEDDING_MODEL_ID,
            body=json.dumps({"inputText": t}),
            contentType="application/json",
            accept="application/json"
        )
        body = json.loads(resp["body"].read())
        vectors.append(body["embedding"])
    return vectors

# --- Simple chunker (char-based) with overlap ---
def chunk_text(text, chunk_size=1500, overlap=200):
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        chunks.append(chunk)
        if end == n: 
            break
        start = end - overlap
        if start < 0:
            start = 0
    return chunks

def extract_pdf_text_from_s3(bucket, key):
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=key)
    file_bytes = obj["Body"].read()
    reader = PdfReader(io.BytesIO(file_bytes))

    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages

def handler(event, context):
    """
    Event options:
    - S3 trigger: event['Records'][0]['s3']['bucket']['name'], key etc.
    - Manual: { "bucket": "...", "key": "...", "category": "sanitation" }
    """
    client = get_os_client()

    if "Records" in event and event["Records"] and "s3" in event["Records"][0]:
        # S3 event
        bucket = event["Records"][0]["s3"]["bucket"]["name"]
        key = event["Records"][0]["s3"]["object"]["key"]
        category = event.get("category", "general")
    else:
        bucket = event["bucket"]
        key = event["key"]
        category = event.get("category", "general")

    pages = extract_pdf_text_from_s3(bucket, key)
    source = f"s3://{bucket}/{key}"

    # Preflight: get one embedding to know vector dimension
    test_vec = embed_texts(["hello world"])[0]
    dim = len(test_vec)
    ensure_index(client, dim)

    # Build docs: chunk per page
    docs_to_index = []
    for page_idx, page_text in enumerate(pages, start=1):
        chunks = chunk_text(page_text)
        for c in chunks:
            if c.strip():
                docs_to_index.append({
                    "text": c,
                    "source": source,
                    "page": page_idx,
                    "category": category
                })

    # Batch embed + index
    # (For simplicity, per-doc calls; for scale, batch these calls)
    for doc in docs_to_index:
        vec = embed_texts([doc["text"]])[0]
        body = {
            "text": doc["text"],
            "source": doc["source"],
            "page": doc["page"],
            "category": doc["category"],
            "embedding": vec
        }
        client.index(index=INDEX_NAME, body=body, refresh=False)

    # Optionally force a refresh at the end (costs a bit)
    # client.indices.refresh(index=INDEX_NAME)
    print(client.cat.indices(format="json"))

    return {
        "statusCode": 200,
        "body": json.dumps({"indexed": len(docs_to_index), "source": source})
    }