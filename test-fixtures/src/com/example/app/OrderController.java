package com.example.app;

/**
 * Top-level entry point — calls OrderService.
 * Exercises deeper call chains for forward/backward traces.
 */
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    public String handleGet(int id) {
        return service.processOrder(id);
    }

    public String handleCheck(int id) {
        boolean exists = service.orderExists(id);
        return exists ? "YES" : "NO";
    }
}
