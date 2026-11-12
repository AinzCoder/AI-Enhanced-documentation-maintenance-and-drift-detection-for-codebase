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