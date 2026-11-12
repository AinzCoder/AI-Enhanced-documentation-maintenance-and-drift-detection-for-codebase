
from rag.llm_generator import (
    generate_documentation_suggestion
)


class_name = "OrderService"
method_name = "getOrder"
change_type = "method_added"

code = """
/**
 * Retrieves an order using its unique identifier.
 */
public void getOrder(int orderId) {
    System.out.println("Getting order: " + orderId);
}
"""

documentation = """
# API Documentation

## OrderService

Provides order management functionality.
"""

developer_comment = (
    "Retrieves an order using its unique identifier."
)

print("Generating documentation suggestion...")

suggestion = generate_documentation_suggestion(
    class_name=class_name,
    method_name=method_name,
    change_type=change_type,
    code=code,
    documentation=documentation,
    developer_comment=developer_comment
)

print("\n===== DEVELOPER COMMENT =====")
print(developer_comment)

print("\n===== AI GENERATED DOCUMENTATION =====")
print(suggestion)
