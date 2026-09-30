from approval.documentation_approval import (
    show_documentation_suggestion
)


suggestion = """
## OrderService

### getOrder(int orderId)

Retrieves an order by its ID.

**Parameters:**

- orderId (int): The ID of the order.
"""


status, final_documentation = (
    show_documentation_suggestion(
        suggestion
    )
)


print("\n===== RESULT =====")
print("Status:", status)

if final_documentation:

    print("\n===== FINAL DOCUMENTATION =====")
    print(final_documentation)