from rag.change_context_retriever import (
    retrieve_change_context
)

from rag.llm_generator import (
    generate_documentation_suggestion
)


def generate_update_for_change(
    class_name: str,
    method_name: str,
    change_type: str,
    code: str
):

    # Retrieve relevant documentation using RAG
    rag_context = retrieve_change_context(
        class_name=class_name,
        method_name=method_name,
        change_type=change_type,
        top_k=3
    )

    # Combine retrieved documents
    documentation_parts = []

    for document, metadata in zip(
        rag_context["documents"],
        rag_context["metadatas"]
    ):

        documentation_parts.append(
            f"File: {metadata['file']}\n"
            f"{document}"
        )

    documentation = "\n\n".join(
        documentation_parts
    )

    # Send code + retrieved documentation to Qwen
    suggestion = generate_documentation_suggestion(
        class_name=class_name,
        method_name=method_name,
        change_type=change_type,
        code=code,
        documentation=documentation
    )

    return {
        "class": class_name,
        "method": method_name,
        "change_type": change_type,
        "retrieved_documents": rag_context["metadatas"],
        "suggestion": suggestion
    }