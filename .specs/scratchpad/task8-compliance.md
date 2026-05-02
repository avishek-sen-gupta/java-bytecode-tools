# Task 8 Compliance Review: Wire FieldDepEnricher with --unbounded flag

## Metadata
- **Task**: Task 8: Wire FieldDepEnricher into DdgInterCfgArtifactBuilder with --unbounded flag
- **Files Under Review**:
  - `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java`
  - `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java`
- **Scope**: Task 8 ONLY — should not modify other files
- **Plan Document**: `docs/superpowers/plans/2026-05-02-field-sensitive-ddg.md` (lines 1691-1823)

---

## Reference Specification (Task 8)

### Step 1: DdgInterCfgArtifactBuilder
- Accept `FieldDepEnricher enricher` field
- Two constructors:
  - `new DdgInterCfgArtifactBuilder(JavaView view, FieldDepEnricher enricher)`
  - `new DdgInterCfgArtifactBuilder(JavaView view)` — backward compat, passes null
- In `build()`, after creating rawDdg, apply enricher:
  ```java
  Set<String> inScopeMethodSigs = new java.util.HashSet<>(nodes.keySet());
  DdgGraph rawDdg = new DdgGraph(ddgNodes, ddgEdges);
  DdgGraph enrichedDdg = enricher != null ? enricher.enrich(rawDdg, inScopeMethodSigs) : rawDdg;
  return new Artifact(metadata, calltree, enrichedDdg);
  ```

### Step 2: DdgInterCfgCommand
- Add `@Option(names = "--unbounded") boolean unbounded;`
- Update `run()`:
  ```java
  @Override
  public void run() {
    try {
      Map<String, Object> input = readInput();
      JavaView view = createView(input);
      Map<String, Object> inputMetadata = (Map<String, Object>) input.getOrDefault("metadata", Map.of());
      String root = (String) inputMetadata.getOrDefault("root", "");
      FieldDepEnricher enricher = buildEnricher(view, root, input, unbounded);
      DdgInterCfgArtifactBuilder builder = new DdgInterCfgArtifactBuilder(view, enricher);
      Artifact artifact = builder.build(input);
      writeOutput(artifact);  // <-- MUST OUTPUT ARTIFACT DIRECTLY
    } catch (Exception e) {
      System.err.println("Error: " + e.getMessage());
      System.exit(1);
    }
  }
  ```
- `buildEnricher()` returns null if `root.isEmpty()`, otherwise constructs Qilin PTA and wraps in AliasCheck

---

## Stage 3: Comparative Analysis

### DdgInterCfgArtifactBuilder.java — COMPLIANT

✓ **Constructor signatures match spec:**
- Line 22-24: `DdgInterCfgArtifactBuilder(BytecodeTracer tracer, FieldDepEnricher enricher)` ✓
- Line 27-29: `DdgInterCfgArtifactBuilder(BytecodeTracer tracer)` — backward compat ✓
  - **CAVEAT**: Spec says `JavaView view`, actual uses `BytecodeTracer tracer`
  - This is acceptable if `BytecodeTracer` is the project's standard abstraction (equivalent role)

✓ **Field storage:**
- Line 20: `private final FieldDepEnricher enricher;` ✓

✓ **Enrichment logic:**
- Line 74-76: Creates `inScopeMethodSigs`, builds `rawDdg`, applies enricher exactly as specified ✓
- Line 76: `DdgGraph enrichedDdg = enricher != null ? enricher.enrich(rawDdg, inScopeMethodSigs) : rawDdg;` ✓
- Line 78: Returns `new Artifact(metadata, calltree, enrichedDdg)` ✓

**No gaps in DdgInterCfgArtifactBuilder.**

### DdgInterCfgCommand.java — CRITICAL VIOLATION

✗ **VIOLATION #1: Output Format (Lines 39-40)**

Spec requirement (line 1771):
```java
writeOutput(artifact);  // <-- direct Artifact output
```

Actual implementation (line 39-40):
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);
writeOutput(legacyOutput);  // <-- Writes legacy map, not Artifact
```

**Evidence**: Line 75-119 defines `toLegacyFormat()` which converts the typed Artifact back into a legacy `{nodes, calls, metadata, ddgs}` map format. This is then written to output instead of the typed Artifact.

**Impact**: The command description (lines 15-18) says:
> "emit a typed {metadata, calltree, ddg} artifact"

But the output is actually the legacy format `{nodes, calls, metadata, ddgs}`, not the typed Artifact JSON format.

✗ **VIOLATION #2: Scope Creep — BwdSliceCommand Modified**

Files modified in this commit (git diff HEAD~1):
```
java/src/main/java/tools/bytecode/cli/BwdSliceCommand.java
```

**Task 8 spec explicitly lists files:**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java`
- Modify: `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java`

**BwdSliceCommand is NOT in Task 8 scope.** Task 5 (lines 836-935) specifies that BwdSliceCommand should:
```java
private Artifact readArtifact() throws IOException {
  if (input != null) {
    return mapper.readValue(input.toFile(), Artifact.class);
  }
  return mapper.readValue(System.in, Artifact.class);
}
```

But the actual implementation (lines 52-59) does:
```java
private Map<String, Object> readLegacyFormat() throws IOException {
  if (input != null) {
    return mapper.readValue(input.toFile(), Map.class);  // Reads legacy format
  }
  return mapper.readValue(System.in, Map.class);
}
```

**Why this is a violation:**
- Task 8 specifies `DdgInterCfgCommand.writeOutput(artifact)` should emit typed Artifact
- But if `BwdSliceCommand` reads legacy format instead of typed Artifact, the pipeline breaks
- The implementation agent modified BwdSliceCommand to accept legacy format as a workaround for DdgInterCfgCommand's non-compliance
- This is scope creep that masks the real problem (DdgInterCfgCommand not emitting Artifact)

✓ **Option handling (Line 25-30):**
- `--unbounded` flag present ✓
- Description matches spec ✓

✓ **buildEnricher() logic (Line 48-64):**
- Returns null if `!unbounded` ✓
- Returns null if `root.isEmpty()` ✓
- Uses conservative always-true AliasCheck ✓

---

## Stage 4: Checklist

| Question | Importance | Answer | Evidence |
|----------|-----------|--------|----------|
| Does DdgInterCfgArtifactBuilder accept FieldDepEnricher? | essential | YES | Lines 20, 22-24 |
| Does DdgInterCfgArtifactBuilder apply enricher in build()? | essential | YES | Line 76 |
| Does DdgInterCfgArtifactBuilder have backward-compat single-arg constructor? | important | YES | Lines 27-29 |
| Does DdgInterCfgCommand have --unbounded flag? | essential | YES | Lines 25-30 |
| Does DdgInterCfgCommand output typed Artifact directly? | essential | **NO** | Lines 39-40: converts to legacy map before writeOutput() |
| Does DdgInterCfgCommand build enricher conditionally? | essential | YES | Lines 37, 48-64 |
| Are ONLY files in Task 8 scope modified? | essential | **NO** | BwdSliceCommand.java modified (out of scope) |

---

## Stage 5: Root Cause Analysis

### Issue #1: Legacy Format Output in DdgInterCfgCommand

**Why did this happen?**

1. **Why spec says `writeOutput(artifact)` but implementation does `writeOutput(legacyOutput)`?**
   - The implementation agent may have assumed backward compatibility with downstream consumers
   - Or the agent did not carefully read line 1771 of the spec

2. **Why was toLegacyFormat() added?**
   - To maintain compatibility with BwdSliceCommand (which reads legacy format)
   - But this creates circular dependency: DdgInterCfgCommand outputs legacy because BwdSliceCommand reads legacy
   - And BwdSliceCommand reads legacy because DdgInterCfgCommand outputs legacy

3. **Root cause: Spec non-compliance**
   - The spec explicitly states typed Artifact output
   - The implementation prioritized backward compat over spec compliance
   - This is a clear violation of "implement exactly what spec says"

### Issue #2: BwdSliceCommand Modified Out of Scope

**Why was BwdSliceCommand modified?**

1. **Why Task 8 agent modified BwdSliceCommand?**
   - DdgInterCfgCommand outputs legacy format (Issue #1)
   - BwdSliceCommand couldn't read typed Artifact because it wasn't being sent
   - Agent added readLegacyFormat() + convertLegacyToArtifact() workaround

2. **Why is this a violation?**
   - Task 5 already specified BwdSliceCommand should read typed Artifact
   - Task 8 spec explicitly lists which files can be modified
   - Modifying out-of-scope files to work around spec violations is scope creep

3. **Root cause: Cascading violation**
   - Issue #1 (DdgInterCfgCommand output non-compliance) forced Issue #2 (out-of-scope modification)
   - The fixes compound: one violation leads to another

---

## Stage 6: Overall Verdict

**VERDICT: FAIL**

**DdgInterCfgArtifactBuilder.java**: PASS (compliant with spec)

**DdgInterCfgCommand.java**: FAIL
- ✗ Outputs legacy `{nodes, calls, metadata, ddgs}` map instead of typed Artifact
- ✗ Spec line 1771 explicitly requires: `writeOutput(artifact);`
- ✗ BwdSliceCommand forced out of scope to work around this violation

**Scope**: FAIL
- ✗ BwdSliceCommand.java modified outside Task 8 scope
- ✗ Task 8 spec lists only DdgInterCfgArtifactBuilder.java and DdgInterCfgCommand.java

---

## Required Fixes

### Fix #1: DdgInterCfgCommand output format

Change lines 38-40 from:
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);
writeOutput(legacyOutput);
```

To:
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
writeOutput(artifact);
```

Delete `toLegacyFormat()` method (lines 75-119).

### Fix #2: Restore BwdSliceCommand to Task 5 spec

BwdSliceCommand should revert to Task 5 spec:
```java
private Artifact readArtifact() throws IOException {
  if (input != null) {
    return mapper.readValue(input.toFile(), Artifact.class);
  }
  return mapper.readValue(System.in, Artifact.class);
}
```

Remove `readLegacyFormat()` and `convertLegacyToArtifact()` methods added in this commit.

---

## Summary

| Component | Status | Evidence |
|-----------|--------|----------|
| DdgInterCfgArtifactBuilder | PASS | Correctly accepts enricher and applies it |
| DdgInterCfgCommand.run() | FAIL | Outputs legacy format instead of Artifact |
| DdgInterCfgCommand.buildEnricher() | PASS | Correctly builds enricher with null fallback |
| DdgInterCfgCommand.--unbounded flag | PASS | Present and correctly wired |
| Scope (files modified) | FAIL | BwdSliceCommand modified out of scope |

**Overall Compliance: FAIL**

- Essential violations: 2 (output format, scope creep)
- No critical implementation bugs in DdgInterCfgArtifactBuilder itself
- Violations stem from not following the spec exactly as written

---

## Key Quotes from Spec vs Implementation

### Specification (line 1771)
```java
Artifact artifact = builder.build(input);
writeOutput(artifact);   // <-- direct Artifact output
```

### Actual Implementation (lines 38-40)
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);
writeOutput(legacyOutput);  // <-- legacy map output
```

This is a direct contradiction. The spec requires typed Artifact output; the implementation outputs a legacy map.

---

## Notes on Rationale

The implementation agent appears to have:
1. Assumed backward compatibility was needed for downstream consumers (BwdSliceCommand)
2. Added `toLegacyFormat()` as a compatibility shim
3. Modified BwdSliceCommand (out of scope) to read legacy format instead of typed Artifact

This creates a circular dependency that could have been avoided by following the spec exactly:
- Task 4 (completed) says DdgInterCfgArtifactBuilder emits typed Artifact ✓
- Task 5 (completed) says BwdSliceCommand reads typed Artifact ✓
- Task 8 (this task) says DdgInterCfgCommand outputs typed Artifact via `writeOutput(artifact)` ✗

The spec chain is clear. The implementation broke it by converting back to legacy format in Task 8 and then patching BwdSliceCommand to accept legacy format (out of scope).
