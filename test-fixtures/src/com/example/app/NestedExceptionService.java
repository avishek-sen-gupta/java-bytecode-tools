package com.example.app;

public class NestedExceptionService {
    public void nestedHandle(int i) {
        try {
            try {
                if (i == 0) throw new Exception("Inner");
            } catch (Exception e) {
                System.out.println("Inner catch");
                if (i < 0) throw new RuntimeException("Outer");
            }
        } catch (RuntimeException e) {
            System.out.println("Outer catch");
        }
    }
}
