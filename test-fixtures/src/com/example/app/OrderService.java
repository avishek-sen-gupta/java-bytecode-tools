package com.example.app;

/**
 * Service layer — calls the repository.
 * Multiple methods call the repo, giving backward trace multiple entry points.
 * Branch logic in processOrder exercises CFG branches.
 */
public class OrderService {
    private final OrderRepository repo;

    public OrderService(OrderRepository repo) {
        this.repo = repo;
    }

    /** Forward trace entry — has branches + calls to repo. */
    public String processOrder(int id) {
        String order = repo.findById(id);
        if (order == null) {
            return "NOT_FOUND";
        }
        String result = transform(order);
        repo.save(result);
        return result;
    }

    /** Second caller of repo.findById — gives backward trace >1 entry point. */
    public boolean orderExists(int id) {
        String order = repo.findById(id);
        return order != null;
    }

    private String transform(String order) {
        return order.toUpperCase();
    }
}
