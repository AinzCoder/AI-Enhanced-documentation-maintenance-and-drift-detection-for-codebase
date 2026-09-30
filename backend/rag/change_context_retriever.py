from rag.embedding_generator import generate_embedding
from rag.vector_store import search_documents


def retrieve_change_context(
    class_name: str,
    method_name: str,
    change_type: str,
    top_k: int = 3
):
    query = (
        f"Documentation for the {change_type} "
        f"of method {method_name} "
        f"in class {class_name}"
    )

    query_embedding = generate_embedding(query)

    results = search_documents(
        query_embedding,
        top_k=top_k
    )

    return {
        "query": query,
        "documents": results["documents"][0],
        "metadatas": results["metadatas"][0],
        "distances": results["distances"][0]
    }