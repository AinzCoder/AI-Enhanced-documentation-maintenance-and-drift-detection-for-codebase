from rag.repository_context_retriever import retrieve_repository_context


def retrieve_change_context(
    class_name: str,
    method_name: str,
    change_type: str,
    top_k: int = 3,
    repository_path: str | None = None,
    source_file: str | None = None
):
    query = (
        f"Documentation for the {change_type} of method {method_name} "
        f"in class {class_name}"
    )
    if source_file:
        query += f" in source file {source_file}"

    if not repository_path:
        return {
            "query": query,
            "repository_id": None,
            "available": False,
            "error": "repository_path_required_for_scoped_retrieval",
            "documents": [],
            "metadatas": [],
            "distances": [],
            "context_characters": 0
        }

    try:
        return retrieve_repository_context(
            repository_path=repository_path,
            query=query,
            top_k=top_k
        )
    except Exception:
        return {
            "query": query,
            "repository_id": None,
            "available": False,
            "error": "repository_scoped_retrieval_unavailable",
            "documents": [],
            "metadatas": [],
            "distances": [],
            "context_characters": 0
        }
