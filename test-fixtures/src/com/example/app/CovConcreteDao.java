package com.example.app;

/**
 * Covariant return type override — javac generates a bridge method
 * {@code Object lookup(String)} at the class declaration line that
 * delegates to the real {@code String lookup(String)} implementation.
 */
public class CovConcreteDao implements CovBaseDao {
    @Override
    public String lookup(String key) {
        return "value-" + key;
    }
}
