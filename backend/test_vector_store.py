from rag.embedding_generator import generate_embedding

from rag.vector_store import (
    add_document,
    search_documents
)


text = """
# API Documentation

## OrderService

Provides order management functionality.
"""


embedding = generate_embedding(text)


add_document(
    document_id="api_chunk_1",
    text=text,
    embedding=embedding,
    metadata={
        "file": "docs/API.md",
        "type": "documentation"
    }
)


print("===== DOCUMENT STORED =====")

print("ID: api_chunk_1")


results = search_documents(
    embedding,
    top_k=1
)


print("\n===== SEARCH RESULT =====")

print(results)