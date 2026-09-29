import chromadb


client = chromadb.PersistentClient(
    path="./chroma_db"
)


collection = client.get_or_create_collection(
    name="documentation"
)


def add_document(
    document_id: str,
    text: str,
    embedding: list[float],
    metadata: dict
):
    collection.add(
        ids=[document_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[metadata]
    )


def search_documents(
    embedding: list[float],
    top_k: int = 3
):
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k
    )

    return results