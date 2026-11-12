from rag.change_context_retriever import (
    retrieve_change_context
)


result = retrieve_change_context(
    class_name="OrderService",
    method_name="getOrder",
    change_type="method_added",
    top_k=3
)


print("===== RAG QUERY =====")

print(result["query"])


print("\n===== RETRIEVED CONTEXT =====")

for index, document in enumerate(
    result["documents"]
):

    print(
        f"\n--- Document {index + 1} ---"
    )

    print(document)

    print(
        "Metadata:",
        result["metadatas"][index]
    )

    print(
        "Distance:",
        result["distances"][index]
    )