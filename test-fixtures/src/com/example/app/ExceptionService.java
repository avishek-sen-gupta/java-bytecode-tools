package com.example.app;

public class ExceptionService {
    public void handleException(int i) {
        try {
            if (i > 0) {
                System.out.println("Positive");
            } else {
                throw new RuntimeException("Negative");
            }
        } catch (RuntimeException e) {
            System.err.println("Caught: " + e.getMessage());
        } finally {
            System.out.println("Done");
        }
    }
}
