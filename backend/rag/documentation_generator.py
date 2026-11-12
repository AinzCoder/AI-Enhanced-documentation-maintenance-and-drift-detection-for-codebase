
from rag.change_context_retriever import (
    retrieve_change_context
)

from rag.llm_generator import (
    generate_documentation_suggestion
)
from rag.indexer import index_repository_documentation


def generate_update_for_change(
    class_name: str,
    method_name: str,
    change_type: str,
    code: str,
    developer_comment: str | None = None,
    repository_path: str | None = None,
    source_file: str | None = None
):
    index_summary = None
    if repository_path:
        try:
            index_summary = index_repository_documentation(repository_path)
        except Exception as error:
            index_summary = {
                "errors": [{
                    "stage": "indexing",
                    "message": f"Repository indexing unavailable ({type(error).__name__})."
                }]
            }

    rag_context = retrieve_change_context(
        class_name=class_name,
        method_name=method_name,
        change_type=change_type,
        top_k=3,
        repository_path=repository_path,
        source_file=source_file
    )

    documentation_parts = []

    for document, metadata in zip(
        rag_context["documents"],
        rag_context["metadatas"]
    ):
        documentation_parts.append(
            f"File: {metadata.get('documentation_file', '(unknown)')}\n"
            f"Section: {metadata.get('section_heading', '(document)')}\n"
            "Supporting repository documentation; verify against current "
            f"source:\n{document}"
        )

    documentation = "\n\n".join(documentation_parts)

    suggestion = generate_documentation_suggestion(
        class_name=class_name,
        method_name=method_name,
        change_type=change_type,
        code=code,
        documentation=documentation,
        developer_comment=developer_comment
    )

    target_documentation = None

    if rag_context["metadatas"]:
        target_documentation = (
            rag_context["metadatas"][0].get("documentation_file")
        )

    return {
        "class": class_name,
        "method": method_name,
        "change_type": change_type,
        "target_documentation": target_documentation,
        "retrieved_documents": rag_context["metadatas"],
        "suggestion": suggestion,
        "rag_retrieval": {
            "repository_scoped": bool(repository_path),
            "repository_id": rag_context.get("repository_id"),
            "vector_store_used": bool(documentation_parts),
            "fallback_used": False,
            "fallback_strategy": (
                "none; unscoped retrieval is disabled"
                if not documentation_parts
                else None
            ),
            "available": rag_context.get("available", False),
            "error": rag_context.get("error"),
            "indexing": index_summary
        }
    }
