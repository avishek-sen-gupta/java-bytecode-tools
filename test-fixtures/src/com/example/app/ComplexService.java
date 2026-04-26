package com.example.app;

public class ComplexService {
    private final ExceptionService excSvc = new ExceptionService();

    public void entryMethod(int i) {
        System.out.println("Starting complex operation");
        excSvc.handleException(i);
        excSvc.handleException(i + 1);
        System.out.println("Finished complex operation");
    }
}
