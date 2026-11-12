import hashlib
import hashlib
from pathlib import Path

from rag.embedding_generator import generate_embedding
from rag.vector_store import get_repository_documents, search_documents
from repository_identity import get_repository_identity
from timing import timed


MAX_TOP_K = 10
MAX_CONTEXT_CHARACTERS = 6000


def _chunk_matches_current_file(repository: Path, metadata: dict) -> bool:
    relative_file = metadata.get("documentation_file")
    expected_hash = metadata.get("content_hash")
    if not relative_file or not expected_hash:
        return False
    path = Path(relative_file)
    if path.is_absolute() or ".." in path.parts:
        return False
    resolved = (repository / path).resolve()
    if not resolved.is_relative_to(repository) or not resolved.is_file():
        return False
    try:
        current_hash = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError:
        return False
    return current_hash == expected_hash


@timed("rag.retrieval")
def retrieve_repository_context(
    repository_path: str,
    query: str,
    top_k: int = 3
) -> dict:
    repository = Path(repository_path).expanduser().resolve()
    repository_id = get_repository_identity(repository)
    if not query.strip() or top_k <= 0:
        return {
            "query": query,
            "repository_id": repository_id,
            "available": True,
            "error": None,
            "documents": [],
            "metadatas": [],
            "distances": [],
            "context_characters": 0
        }

    limited_top_k = min(top_k, MAX_TOP_K)
    try:
        embedding = generate_embedding(query)
        results = search_documents(
            embedding,
            top_k=limited_top_k,
            repository_id=repository_id
        )
        raw_documents = (results.get("documents") or [[]])[0] or []
        raw_metadatas = (results.get("metadatas") or [[]])[0] or []
        raw_distances = (results.get("distances") or [[]])[0] or []
        documents = []
        metadatas = []
        distances = []
        seen_chunks = set()
        remaining_characters = MAX_CONTEXT_CHARACTERS
        for index, (document, metadata) in enumerate(
            zip(raw_documents, raw_metadatas)
        ):
            if not isinstance(document, str) or not document:
                continue
            metadata = metadata or {}
            if (
                metadata.get("repository_id") != repository_id
                or metadata.get("source_type") != "documentation"
                or not _chunk_matches_current_file(repository, metadata)
            ):
                continue
            content_hash = metadata.get("content_hash")
            chunk_index = metadata.get("chunk_index")
            deduplication_key = (
                (content_hash, chunk_index)
                if content_hash is not None and chunk_index is not None
                else hashlib.sha256(document.encode("utf-8")).hexdigest()
            )
            if deduplication_key in seen_chunks:
                continue
            seen_chunks.add(deduplication_key)
            if remaining_characters <= 0:
                break
            bounded_document = document[:remaining_characters]
            documents.append(bounded_document)
            metadatas.append(metadata)
            distances.append(
                raw_distances[index]
                if index < len(raw_distances)
                else None
            )
            remaining_characters -= len(bounded_document)

        return {
            "query": query,
            "repository_id": repository_id,
            "available": True,
            "error": None,
            "documents": documents,
            "metadatas": metadatas,
            "distances": distances,
            "context_characters": (
                MAX_CONTEXT_CHARACTERS - remaining_characters
            )
        }
    except Exception:
        return {
            "query": query,
            "repository_id": repository_id,
            "available": False,
            "error": "repository_vector_retrieval_unavailable",
            "documents": [],
            "metadatas": [],
            "distances": [],
            "context_characters": 0
        }


def get_repository_index_status(repository_path: str) -> dict:
    repository = Path(repository_path).expanduser().resolve()
    repository_id = get_repository_identity(repository)
    try:
        indexed = get_repository_documents(repository_id)
        file_names = {
            metadata.get("documentation_file")
            for metadata in indexed.get("metadatas", [])
            if metadata.get("source_type") == "documentation"
            and metadata.get("documentation_file")
        }
        chunk_count = sum(
            1
            for metadata in indexed.get("metadatas", [])
            if metadata.get("source_type") == "documentation"
        )
        return {
            "repository": repository.name,
            "repository_id": repository_id,
            "index_available": True,
            "indexed_document_count": len(file_names),
            "chunk_count": chunk_count,
            "last_successful_indexing": None
        }
    except Exception:
        return {
            "repository": repository.name,
            "repository_id": repository_id,
            "index_available": False,
            "indexed_document_count": None,
            "chunk_count": None,
            "last_successful_indexing": None
        }
