package com.example.app;

/** Interface with Object return type — forces bridge method generation on covariant impls. */
public interface CovBaseDao {
    Object lookup(String key);
}
