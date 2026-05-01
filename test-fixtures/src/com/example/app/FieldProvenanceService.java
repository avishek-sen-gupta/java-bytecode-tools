package com.example.app;

public class FieldProvenanceService {

  private int count;
  private int base;

  public void update(int delta) {
    int base = this.base;
    int result = base + delta;
    this.count = result;
  }

  public int read() {
    int value = this.count;
    return value;
  }

  public void caller() {
    update(10);
    read();
  }
}
