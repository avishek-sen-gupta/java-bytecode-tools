package com.example.app;

/** Interface — tests polymorphic dispatch in call graph. */
public interface OrderRepository {
    String findById(int id);
    void save(String order);
}
