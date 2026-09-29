from rag.context_retriever import retrieve_context


repository_path = "../test_repositories/OrderManagement"

code_file = "src/OrderService.java"

documentation_files = [
    "README.md",
    "docs/API.md"
]


context = retrieve_context(
    repository_path,
    code_file,
    documentation_files,
    "OrderService",
    "getOrder"
)


print("===== CLASS =====")
print(context["class"])

print("\n===== METHOD =====")
print(context["method"])

print("\n===== CODE =====")
print(context["code"])

print("\n===== DOCUMENTATION =====")

for documentation in context["documentation"]:

    print("\nFile:", documentation["file"])

    print(documentation["content"])