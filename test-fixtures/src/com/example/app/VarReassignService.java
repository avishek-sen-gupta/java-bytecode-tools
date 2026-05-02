package com.example.app;

public class VarReassignService {
  // Conditional reassignment: forces SootUp to emit non-SSA Jimple (no variable versioning).
  // Straight-line methods get SSA-versioned locals (value#0, value#1), masking the
  // last-writer-wins bug. With an if-branch, 'value' is unversioned on both sides
  // of the assignment, matching a real-world pattern where a DAO method
  // conditionally reassigns a local before passing it to a query builder.
  public String sanitize(String value) {
    if (value.indexOf("*") >= 0) {
      value = value.replace("*", "%");
    }
    return value;
  }
}
