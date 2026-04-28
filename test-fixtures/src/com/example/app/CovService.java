package com.example.app;

/** Caller — invokes CovConcreteDao through the interface, triggering bridge method dispatch. */
public class CovService {
    private final CovBaseDao dao;

    public CovService(CovBaseDao dao) {
        this.dao = dao;
    }

    public Object fetchItem(String key) {
        return dao.lookup(key);
    }
}
