package com.example.app;

/** Concrete impl — call graph should resolve OrderRepository → JdbcOrderRepository. */
public class JdbcOrderRepository implements OrderRepository {
    @Override
    public String findById(int id) {
        if (id <= 0) {
            return null;
        }
        return "order-" + id;
    }

    @Override
    public void save(String order) {
        System.out.println("Saving: " + order);
    }
}
