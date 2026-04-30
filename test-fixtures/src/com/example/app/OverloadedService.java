package com.example.app;

/** Test fixture: two overloads of process() for resolveMethodByName ambiguity tests. */
public class OverloadedService {
    public String process(int id) {
        return "int:" + id;
    }

    public String process(String name) {
        return "str:" + name;
    }

    public String unique() {
        return "unique";
    }
}
