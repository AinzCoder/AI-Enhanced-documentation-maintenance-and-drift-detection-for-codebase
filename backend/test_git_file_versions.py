from git_analysis.git_analyzer import get_file_from_commit


repository_path = "../test_repositories/OrderManagement"

old_commit = "624da1cbfe6c4d5cade01e18d8dc4b7c004d7f5e"
new_commit = "98c72c65fdafaed7160d2f8b7f9f54ab9cfbdf89"

file_path = "src/OrderService.java"


old_code = get_file_from_commit(
    repository_path,
    old_commit,
    file_path
)

new_code = get_file_from_commit(
    repository_path,
    new_commit,
    file_path
)


print("===== OLD VERSION =====")
print(old_code.decode("utf-8"))

print("\n===== NEW VERSION =====")
print(new_code.decode("utf-8"))