from approval.documentation_updater import (
    update_method_documentation
)


result = update_method_documentation(
    repository_path="../test_repositories/OrderManagement",
    documentation_file="docs/API.md",
    class_name="OrderService",
    method_name="getOrder",
    new_documentation="""
### getOrder(int orderId)

Retrieves an existing order by its ID.

**Parameters:**

- `orderId` (int): The ID of the order to retrieve.
"""
)

print("===== UPDATE RESULT =====")
print(result)