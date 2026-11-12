from pathlib import Path

import chromadb
from timing import timed


CHROMA_PATH = Path(__file__).resolve().parents[1] / "chroma_db"
COLLECTION_NAME = "documentation"
UPSERT_BATCH_SIZE = 100

@timed("chroma.open")
def _open_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    return client, client.get_or_create_collection(name=COLLECTION_NAME)


client, collection = _open_collection()


def _repository_filter(repository_id: str) -> dict:
    if not repository_id:
        raise ValueError("A repository_id is required for vector operations.")
    return {"repository_id": repository_id}


@timed("chroma.upsert_one")
def add_document(
    document_id: str,
    text: str,
    embedding: list[float],
    metadata: dict
):
    if not metadata.get("repository_id"):
        raise ValueError("Indexed documents must include repository_id metadata.")
    collection.upsert(
        ids=[document_id],
        documents=[text],
        embeddings=[embedding],
        metadatas=[metadata]
    )


@timed("chroma.upsert")
def add_documents(
    documents: list[dict],
    preserve_ids: set[str] | None = None
) -> None:
    if not documents:
        return
    for item in documents:
        if not item.get("metadata", {}).get("repository_id"):
            raise ValueError(
                "Indexed documents must include repository_id metadata."
            )

    try:
        for offset in range(0, len(documents), UPSERT_BATCH_SIZE):
            batch = documents[offset:offset + UPSERT_BATCH_SIZE]
            collection.upsert(
                ids=[item["id"] for item in batch],
                documents=[item["text"] for item in batch],
                embeddings=[item["embedding"] for item in batch],
                metadatas=[item["metadata"] for item in batch]
            )
    except Exception:
        try:
            protected_ids = preserve_ids or set()
            collection.delete(ids=[
                item["id"]
                for item in documents
                if item["id"] not in protected_ids
            ])
        except Exception as cleanup_error:
            raise RuntimeError(
                "Vector upsert failed and partial new chunks could not be "
                f"cleaned up ({type(cleanup_error).__name__})."
            ) from cleanup_error
        raise


@timed("chroma.search")
def search_documents(
    embedding: list[float],
    top_k: int = 3,
    repository_id: str | None = None
):
    repository_filter = _repository_filter(repository_id or "")
    results = collection.query(
        query_embeddings=[embedding],
        n_results=top_k,
        where={
            "$and": [
                repository_filter,
                {"source_type": "documentation"}
            ]
        },
        include=["documents", "metadatas", "distances"]
    )
    return results


@timed("chroma.get_repository_documents")
def get_repository_documents(repository_id: str) -> dict:
    repository_filter = _repository_filter(repository_id)
    return collection.get(
        where=repository_filter,
        include=["metadatas"]
    )


@timed("chroma.get_chunk_embeddings")
def get_chunk_embeddings(document_ids: list[str], repository_id: str) -> dict:
    if not document_ids:
        return {"documents": [], "embeddings": []}
    return collection.get(
        ids=document_ids,
        where=_repository_filter(repository_id),
        include=["documents", "embeddings"]
    )


@timed("chroma.delete_documents")
def delete_documents(document_ids: list[str]) -> None:
    if document_ids:
        collection.delete(ids=document_ids)


@timed("chroma.delete_repository_documents")
def delete_repository_documents(
    repository_id: str,
    documentation_file: str | None = None
) -> int:
    repository_documents = get_repository_documents(repository_id)
    ids = repository_documents.get("ids", [])
    metadatas = repository_documents.get("metadatas", [])
    selected_ids = [
        document_id
        for document_id, metadata in zip(ids, metadatas)
        if (
            documentation_file is None
            or metadata.get("documentation_file") == documentation_file
        )
    ]
    delete_documents(selected_ids)
    return len(selected_ids)


@timed("chroma.clear_collection")
def clear_collection(repository_id: str | None = None) -> None:
    if not repository_id:
        raise ValueError(
            "Global collection clearing is disabled; provide repository_id."
        )
    delete_repository_documents(repository_id)
