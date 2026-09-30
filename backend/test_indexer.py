from repository.repository_scanner import scan_repository

from rag.indexer import index_documentation


repository_path = "../test_repositories/OrderManagement"


repository_info = scan_repository(
    repository_path
)


print("===== DOCUMENTATION FILES =====")

for file in repository_info.documentation_files:
    print(file)


count = index_documentation(
    repository_path,
    repository_info.documentation_files
)


print("\n===== INDEXING RESULT =====")

print("Chunks indexed:", count)