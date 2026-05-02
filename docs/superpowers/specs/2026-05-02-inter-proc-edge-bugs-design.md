# Fix Inter-Procedural DDG Edge Bugs

## Goal

Fix two bugs preventing inter-procedural PARAM and RETURN edges from being generated for interface-dispatched method calls.

## Bug 1: Signature mismatch in `InterProcEdgeBuilder`

### Problem

`InterProcEdgeBuilder` matches call-site nodes against calltree edges using exact signature comparison (`equals()`). Calltree edges contain resolved concrete class signatures (e.g., `<com.example.dao.DaoImpl: List findByCriteria(Map)>`), but Jimple call-site nodes retain the declared interface signature (e.g., `<com.example.dao.IDao: List findByCriteria(Map)>`). The comparison always fails for interface-dispatched calls, so no PARAM or RETURN edges are emitted.

### Fix

Replace exact signature comparison with sub-signature matching. A sub-signature is the method name + parameter types, ignoring the declaring class. For example, from `<com.example.Foo: int bar(String,int)>`, the sub-signature is `bar(String,int)`.

Extract the sub-signature from both:
- The calltree's callee signature (already known)
- The call-site node's `targetMethodSignature`

Compare sub-signatures instead of full signatures.

### Affected code

- `InterProcEdgeBuilder.java` `buildReturnEdges()`: line 68, `callee.equals(n.call().get("targetMethodSignature"))`
- `InterProcEdgeBuilder.java` `buildParamEdges()`: line 172, `calleeSig.equals(n.call().get("targetMethodSignature"))`

### Why sub-signature matching is safe

The calltree already resolved virtual/interface dispatch. Within one calltree edge `{from: caller, to: callee}`, we are only matching call-site nodes in the caller that target that specific callee. Sub-signature collision would require the same caller to invoke two different interfaces with identical method names and parameter types that both resolve to different methods on the same concrete class — this does not occur in practice.

### Implementation

`InterProcEdgeBuilder` is currently a static-methods-only class. Convert it to an instance-based class with instance methods. All public methods (`build`, `buildParamEdges`, `buildReturnEdges`, `extractArgLocal`, `findReachingDefId`, `isConstantArg`) become instance methods.

Add an instance method `extractSubSignature(String methodSignature)` that extracts `methodName(paramTypes)` from a full Soot method signature. Use it in both `buildReturnEdges` and `buildParamEdges` to compare call-site targets against calltree callee signatures.

Pattern for Soot signatures: `<ClassName: ReturnType methodName(ParamType1,ParamType2)>`. The sub-signature is everything from the method name through the closing parenthesis.

Update `DdgInterCfgArtifactBuilder` to instantiate `InterProcEdgeBuilder` and call instance methods instead of static methods.

## Bug 2: SSA `#` missing from `classifyStmt` regex

### Problem

`DdgInterCfgMethodGraphBuilder.classifyStmt()` uses the regex `^\\w[\\w$]*` to detect assignment-invoke statements. SSA-versioned variables (e.g., `localVar#1`) contain `#`, which is not matched by `\\w` or `$`. Statements like `localVar#1 = interfaceinvoke ...` fall through to `INVOKE` instead of `ASSIGN_INVOKE`.

This causes `buildReturnEdges` to miss these nodes (it looks for `ASSIGN_INVOKE` kind), so RETURN edges are not generated even when signature matching succeeds.

### Fix

Change `^\\w[\\w$]*` to `^\\w[\\w$#]*` on line 54 of `DdgInterCfgMethodGraphBuilder.java`.

### Note

The other regex patterns on lines 22-24 (`ASSIGN_LOCAL`, `IDENTITY_LOCAL`, `RETURN_VAL`) already include `#`. This is the only pattern that was missed.

## Testing

### Bug 2 (regex fix)

- Unit test: `classifyStmt` returns `ASSIGN_INVOKE` for `localVar#1 = interfaceinvoke ...`
- Unit test: `classifyStmt` still returns `ASSIGN_INVOKE` for non-SSA `x = virtualinvoke ...`

### Bug 1 (sub-signature matching)

- Unit test: `extractSubSignature` extracts correctly from full Soot signatures
- Unit test: `buildReturnEdges` matches when sub-signatures match but declaring classes differ
- Unit test: `buildParamEdges` matches when sub-signatures match but declaring classes differ
- Integration test: build DDG with interface-dispatched call, verify PARAM and RETURN edges exist

### E2E

- Extend or add shell test: `ddg-inter-cfg | bwd-slice` traces parameters across an interface-dispatched call boundary

## Out of scope

- Multiple dispatch targets for the same call site (polymorphic call sites with multiple concrete receivers)
- Receiver (`@this`) wiring (handled by `FieldDepEnricher`)
