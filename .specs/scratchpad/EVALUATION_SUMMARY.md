# Task 8 Spec Compliance Evaluation — FINAL VERDICT

## VERDICT: FAIL ❌

**Status**: Non-Mergeable | **Severity**: CRITICAL | **Essential Violations**: 2

---

## The Two Critical Violations

### VIOLATION 1: Wrong Output Format (DdgInterCfgCommand)

**What the spec requires (line 1771):**
```java
Artifact artifact = builder.build(input);
writeOutput(artifact);  // Output typed Artifact
```

**What the code actually does (lines 38-40):**
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);  // WRONG!
writeOutput(legacyOutput);  // Outputs legacy {nodes, calls, metadata, ddgs}
```

**Why this is critical**: The command description claims "emit a typed artifact" but actually emits a legacy map. This breaks the entire typed artifact pipeline specified in Tasks 2-4.

---

### VIOLATION 2: Out-of-Scope File Modification (BwdSliceCommand)

**Task 8 scope (line 1693-1695):**
- Modify: `java/src/main/java/tools/bytecode/DdgInterCfgArtifactBuilder.java`
- Modify: `java/src/main/java/tools/bytecode/cli/DdgInterCfgCommand.java`

**What was actually modified:**
- ✓ DdgInterCfgArtifactBuilder.java
- ✓ DdgInterCfgCommand.java
- ✗ **BwdSliceCommand.java** (NOT in Task 8 scope!)

**Why this is critical**: Modifying BwdSliceCommand.java is a scope violation. The agent added this to work around Violation 1 (wrong output format), creating a mask for the real problem.

---

## What Works (Partial Credit)

**DdgInterCfgArtifactBuilder.java**: ✓ FULLY COMPLIANT
- Accepts enricher field ✓
- Has two constructors (2-arg + 1-arg) ✓
- Applies enricher in build() ✓
- Returns typed Artifact ✓

**DdgInterCfgCommand features**: ✓ MOSTLY COMPLIANT
- --unbounded flag present ✓
- buildEnricher() correctly implemented ✓
- Null-safe enricher handling ✓
- **EXCEPT**: Output format is wrong ✗

---

## Why This Happened

The implementation agent prioritized backward compatibility over spec compliance:

1. **Problem**: Task 8 spec says output typed Artifact
2. **Workaround attempted**: Agent added `toLegacyFormat()` to convert back to legacy format
3. **Consequence**: DdgInterCfgCommand now outputs legacy format instead of Artifact
4. **Cascade failure**: BwdSliceCommand couldn't receive typed Artifact (because none was being sent)
5. **Scope violation**: Agent modified BwdSliceCommand (out of scope) to accept legacy format

This created a circular dependency that masked the root problem.

---

## What Needs to Be Fixed

### Fix 1: Delete Legacy Format Conversion (FIX-V1)

In `DdgInterCfgCommand.java`, lines 38-40:

**Remove:**
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);
writeOutput(legacyOutput);
```

**Replace with:**
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
writeOutput(artifact);
```

**Also delete:** The entire `toLegacyFormat()` method (lines 75-119).

### Fix 2: Revert BwdSliceCommand to Task 5 Spec (FIX-V2)

Remove all modifications to `BwdSliceCommand.java` made in this commit:
- Delete `readLegacyFormat()` method
- Delete `convertLegacyToArtifact()` method
- Restore original `readArtifact()` that reads typed Artifact:

```java
private Artifact readArtifact() throws IOException {
  if (input != null) {
    return mapper.readValue(input.toFile(), Artifact.class);
  }
  return mapper.readValue(System.in, Artifact.class);
}
```

---

## Summary Table

| Item | Spec | Actual | Status |
|------|------|--------|--------|
| DdgInterCfgArtifactBuilder enricher field | Required | Implemented | ✓ |
| DdgInterCfgArtifactBuilder.enrich() call | Required | Correct logic | ✓ |
| DdgInterCfgCommand --unbounded flag | Required | Present | ✓ |
| DdgInterCfgCommand buildEnricher() | Required | Correct logic | ✓ |
| **DdgInterCfgCommand output format** | **Artifact** | **Legacy map** | **✗** |
| **Files modified in scope** | **2 only** | **3 (includes BwdSliceCommand)** | **✗** |

---

## Key Spec Quotes

**Spec, line 1771 (what output should be):**
```java
Artifact artifact = builder.build(input);
writeOutput(artifact);
```

**Actual, lines 38-40 (what output actually is):**
```java
Artifact artifact = new DdgInterCfgArtifactBuilder(tracer, enricher).build(inputGraph);
Map<String, Object> legacyOutput = toLegacyFormat(artifact, inputGraph);
writeOutput(legacyOutput);
```

This is a direct contradiction. There is no ambiguity.

---

## Recommendation

**Do not merge.** Both violations must be fixed:

1. Apply FIX-V1 (output format)
2. Apply FIX-V2 (revert BwdSliceCommand)
3. Re-run full test suite
4. Resubmit for evaluation

The implementation is ~95% correct (DdgInterCfgArtifactBuilder is perfect), but the final output interface is wrong and violates scope boundaries. These are not minor issues — they break the artifact pipeline design.

---

## Files for Review

- Scratchpad details: `.specs/scratchpad/task8-compliance.md`
- Detailed YAML verdict: `.specs/scratchpad/task8-final-verdict.yaml`
- This summary: `.specs/scratchpad/EVALUATION_SUMMARY.md`
