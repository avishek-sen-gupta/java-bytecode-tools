package com.example.app;

public class RecursionService {
    public void recurse(int i) {
        if (i > 0) {
            recurse(i - 1);
        }
        System.out.println("i=" + i);
    }

    public void entry(int i) {
        recurse(i);
        recurse(i + 1);
    }
}
