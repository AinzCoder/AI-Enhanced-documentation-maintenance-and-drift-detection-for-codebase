from rag.documentation_generator import (
    generate_update_for_change
)


result = generate_update_for_change(
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
"""
)

print("===== RETRIEVED DOCUMENTS =====")

for document in result["retrieved_documents"]:
    print(document)

print("\n===== AI SUGGESTION =====")
print(result["suggestion"])