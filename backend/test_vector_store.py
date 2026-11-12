from rag.embedding_generator import generate_embedding

from rag.vector_store import (
    add_document,
    search_documents
)


# --------------------------------
# STORE DOCUMENT
# --------------------------------

document = """
# API Documentation

## OrderService

Provides order management functionality.
"""


document_embedding = generate_embedding(
    document
)


add_document(
    document_id="api_chunk_1",
    text=document,
    embedding=document_embedding,
    metadata={
        "file": "docs/API.md",
        "type": "documentation"
    }
)


print("===== DOCUMENT STORED =====")


# --------------------------------
# SEMANTIC SEARCH
# --------------------------------

query = "How does the system handle orders?"


query_embedding = generate_embedding(
    query
)


results = search_documents(
    query_embedding,
    top_k=1
)


print("\n===== QUERY =====")

print(query)


print("\n===== RETRIEVED DOCUMENT =====")

print(results["documents"][0][0])


print("\n===== DISTANCE =====")

print(results["distances"][0][0])