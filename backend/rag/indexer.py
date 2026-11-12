import hashlib
from pathlib import Path

from analyzer.file_scanner import EXCLUDED_DIRECTORIES
from rag.chunker import chunk_markdown
from rag.embedding_generator import EmbeddingModelInitializationError, generate_embedding
from rag.vector_store import (
    add_documents,
    delete_documents,
    get_chunk_embeddings,
    get_repository_documents
)
from repository.repository_scanner import scan_repository
from repository_identity import get_repository_identity
from timing import timed


_EXCLUDED_DOCUMENTATION_DIRECTORIES = EXCLUDED_DIRECTORIES | {
    ".chroma",
    "chroma_db",
    "generated_previews",
    "output",
    "previews"
}


def _relative_documentation_path(
    repository: Path,
    documentation_file: str
) -> tuple[Path, str]:
    path = Path(documentation_file)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Documentation file must be repository-relative.")
    resolved = (repository / path).resolve()
    if not resolved.is_relative_to(repository):
        raise ValueError("Documentation file escapes the repository.")
    relative = resolved.relative_to(repository).as_posix()
    if any(
        part.casefold() in _EXCLUDED_DOCUMENTATION_DIRECTORIES
        for part in Path(relative).parts
    ):
        raise ValueError("Documentation file is in an excluded directory.")
    if "preview" in Path(relative).name.casefold():
        raise ValueError("Generated preview files are not indexed.")
    return resolved, relative


def _existing_repository_documents(repository_id: str) -> dict:
    indexed = get_repository_documents(repository_id)
    result = {}
    for document_id, metadata in zip(
        indexed.get("ids", []),
        indexed.get("metadatas", [])
    ):
        file_name = metadata.get("documentation_file")
        if file_name:
            result.setdefault(file_name, []).append(
                (document_id, metadata)
            )
    return result


def _chunk_id(
    repository_id: str,
    documentation_file: str,
    content_hash: str,
    chunk_index: int,
    text: str
) -> str:
    identity = "\0".join((
        repository_id,
        documentation_file,
        content_hash,
        str(chunk_index),
        hashlib.sha256(text.encode("utf-8")).hexdigest()
    ))
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _index_documentation_files(
    repository: Path,
    repository_id: str,
    documentation_files: list[str],
    existing_documents: dict,
    summary: dict,
    remove_deleted: bool
) -> None:
    normalized_files = []
    for documentation_file in documentation_files:
        try:
            _, relative = _relative_documentation_path(
                repository,
                documentation_file
            )
            normalized_files.append(relative)
        except (OSError, ValueError) as error:
            summary["errors"].append({
                "file": str(documentation_file),
                "stage": "path_validation",
                "message": str(error)
            })

    current_files = set(normalized_files)
    for relative_file in sorted(current_files):
        try:
            file_path, _ = _relative_documentation_path(
                repository,
                relative_file
            )
            file_bytes = file_path.read_bytes()
            content = file_bytes.decode("utf-8")
            content_hash = hashlib.sha256(file_bytes).hexdigest()
            chunks = chunk_markdown(content)
            old_chunks = existing_documents.get(relative_file, [])

            old_hashes = {
                metadata.get("content_hash")
                for _, metadata in old_chunks
            }
            old_indexes = sorted(
                metadata.get("chunk_index")
                for _, metadata in old_chunks
                if isinstance(metadata.get("chunk_index"), int)
            )
            if (
                chunks
                and old_hashes == {content_hash}
                and old_indexes == list(range(len(chunks)))
                and len(old_chunks) == len(chunks)
            ):
                summary["skipped_files"].append(relative_file)
                continue
            if not chunks and not old_chunks:
                summary["skipped_files"].append(relative_file)
                continue

            reusable_embeddings = {}
            if old_chunks and chunks:
                previous = get_chunk_embeddings(
                    [document_id for document_id, _ in old_chunks],
                    repository_id
                )
                previous_texts = previous.get("documents")
                previous_embeddings = previous.get("embeddings")
                if previous_texts is None or previous_embeddings is None or len(previous_texts) != len(previous_embeddings):
                    raise ValueError("Stored chunk embeddings could not be read.")
                for text, embedding in zip(previous_texts, previous_embeddings):
                    if not isinstance(text, str) or embedding is None or len(embedding) != 384:
                        raise ValueError("Stored chunk embedding is invalid.")
                    reusable_embeddings[text] = embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)

            pending_documents = []
            for chunk_index, chunk in enumerate(chunks):
                embedding = reusable_embeddings.get(chunk["text"])
                if embedding is None:
                    embedding = generate_embedding(chunk["text"])
                    reusable_embeddings[chunk["text"]] = embedding
                pending_documents.append({
                    "id": _chunk_id(
                        repository_id,
                        relative_file,
                        content_hash,
                        chunk_index,
                        chunk["text"]
                    ),
                    "text": chunk["text"],
                    "embedding": embedding,
                    "metadata": {
                        "repository_id": repository_id,
                        "documentation_file": relative_file,
                        "section_heading": chunk["section_heading"],
                        "chunk_index": chunk_index,
                        "content_hash": content_hash,
                        "source_type": "documentation"
                    }
                })

            add_documents(
                pending_documents,
                preserve_ids={
                    document_id
                    for document_id, _ in old_chunks
                }
            )
            new_ids = {
                item["id"]
                for item in pending_documents
            }
            stale_ids = [
                document_id
                for document_id, _ in old_chunks
                if document_id not in new_ids
            ]
            delete_documents(stale_ids)
            summary["indexed_files"].append(relative_file)
            summary["indexed_chunks"] += len(pending_documents)
        except (OSError, UnicodeDecodeError, ValueError, EmbeddingModelInitializationError) as error:
            summary["errors"].append({
                "file": relative_file,
                "stage": "document_indexing",
                "message": str(error)
            })
        except Exception as error:
            summary["errors"].append({
                "file": relative_file,
                "stage": "document_indexing",
                "message": (
                    "Embedding or vector storage failed "
                    f"({type(error).__name__})."
                )
            })

    if not remove_deleted:
        return

    for deleted_file in sorted(set(existing_documents) - current_files):
        try:
            delete_documents([
                document_id
                for document_id, _ in existing_documents[deleted_file]
            ])
            summary["deleted_files"].append(deleted_file)
        except Exception as error:
            summary["errors"].append({
                "file": deleted_file,
                "stage": "stale_chunk_cleanup",
                "message": (
                    "Could not remove stale vector chunks "
                    f"({type(error).__name__})."
                )
            })


@timed("rag.index")
def index_repository_documentation(repository_path: str) -> dict:
    repository = Path(repository_path).expanduser().resolve()
    repository_id = get_repository_identity(repository)
    summary = {
        "repository": repository.name,
        "repository_id": repository_id,
        "indexed_files": [],
        "skipped_files": [],
        "deleted_files": [],
        "indexed_chunks": 0,
        "errors": []
    }

    try:
        repository_info = scan_repository(str(repository))
    except Exception as error:
        summary["errors"].append({
            "file": None,
            "stage": "repository_scan",
            "message": (
                "Could not scan repository documentation "
                f"({type(error).__name__})."
            )
        })
        return summary
    try:
        existing_documents = _existing_repository_documents(repository_id)
    except Exception as error:
        summary["errors"].append({
            "file": None,
            "stage": "vector_store_access",
            "message": (
                "Could not access the repository-scoped vector index "
                f"({type(error).__name__})."
            )
        })
        return summary

    documentation_files = [
        file_name
        for file_name in repository_info.documentation_files
        if not any(
            part.casefold() in _EXCLUDED_DOCUMENTATION_DIRECTORIES
            for part in Path(file_name).parts
        )
        and "preview" not in Path(file_name).name.casefold()
    ]
    _index_documentation_files(
        repository,
        repository_id,
        documentation_files,
        existing_documents,
        summary,
        remove_deleted=True
    )
    return summary


@timed("rag.index_selected")
def index_documentation(
    repository_path: str,
    documentation_files: list[str]
):
    repository = Path(repository_path).expanduser().resolve()
    repository_id = get_repository_identity(repository)
    summary = {
        "repository": repository.name,
        "repository_id": repository_id,
        "indexed_files": [],
        "skipped_files": [],
        "deleted_files": [],
        "indexed_chunks": 0,
        "errors": []
    }
    existing_documents = _existing_repository_documents(repository_id)
    _index_documentation_files(
        repository,
        repository_id,
        documentation_files,
        existing_documents,
        summary,
        remove_deleted=False
    )
    if summary["errors"]:
        raise RuntimeError(
            "Some documentation files could not be indexed: "
            + "; ".join(error["stage"] for error in summary["errors"])
        )
    return summary["indexed_chunks"]
