from rag.llm_generator import (
    generate_documentation_suggestion
)


result = generate_documentation_suggestion(
    class_name="OrderService",
    method_name="getOrder",
    change_type="method_added",
    code="""
public class OrderService {

    public void createOrder() {
        System.out.println("Creating order");
    }

    public void cancelOrder(int orderId) {
        System.out.println("Cancelling order: " + orderId);
    }

    public void getOrder(int orderId) {
        System.out.println("Getting order: " + orderId);
    }
}
""",
    documentation="""
# API Documentation

## OrderService

Provides order management functionality.
"""
)

print("===== AI GENERATED DOCUMENTATION =====")
print(result)