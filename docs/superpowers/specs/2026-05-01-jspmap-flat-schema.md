# jspmap Flat Schema Extension Design

## Goal

Replace jspmap's legacy `{meta, actions}` output with the shared flat `{nodes, calls, metadata}` schema, making jspmap output directly consumable by `calltree-print`, `frames-print`, and `calltree-to-dot`. Delete `jspmap_to_dot.py`.

## Architecture

jspmap already loads the buildcg call graph from disk. It will also load `callsites` and `methodLines` from that same JSON (currently ignored), then call `calltree.build_graph()` per entry signature to get the Java call subgraph. It then prepends JSP and EL nodes with their edges and emits a single flat document.

```
JSP parsing → EL actions → entry signatures
                                 ↓
                    calltree.build_graph() (per entry sig)
                                 ↓
         graft JSP/EL prefix → merge → emit {nodes, calls, metadata}
```

Multiple actions sharing a Java method merge naturally: the node appears once, multiple incoming edges preserved.

## Schema Changes

### nodes — two new mandatory fields

Every node gains `node_type` (mandatory, no default). Existing `calltree` and `frames` nodes use `"java_method"`.

| node_type | Key format | Extra fields |
|---|---|---|
| `"java_method"` | JVM sig: `<com.example.Svc: void save()>` | `lineStart`, `lineEnd`, `sourceLineCount` (when available) |
| `"jsp"` | `jsp:/relative/path/to/file.jsp` | none |
| `"el_expression"` | `el:/relative/path/to/file.jsp#${expr}` | `expression` (exact EL string) |

Example JSP node:
```json
"jsp:/views/list.jsp": {
  "node_type": "jsp",
  "class": "/views/list.jsp",
  "method": "",
  "methodSignature": "jsp:/views/list.jsp"
}
```

Example EL node:
```json
"el:/views/list.jsp#${bean.save}": {
  "node_type": "el_expression",
  "class": "/views/list.jsp",
  "method": "${bean.save}",
  "methodSignature": "el:/views/list.jsp#${bean.save}",
  "expression": "${bean.save}"
}
```

### calls — mandatory edge_info

Every call edge gains `edge_info` (mandatory; at minimum `{}`).

| Producer | edge_info |
|---|---|
| calltree / frames — Java→Java | `{}` |
| jspmap JSP→EL | `{"edge_type": "el_call"}` |
| jspmap EL→Java entry (or JSP→Java when no EL) | `{"edge_type": "method_call"}` |
| jspmap Java→Java (from calltree subgraph) | `{}` |

### metadata

```json
{
  "tool": "jspmap",
  "jsps_root": "/path/to/webroot",
  "faces_config": "/path/to/faces-config.xml",
  "call_graph": "/path/to/cg.json",
  "dao_pattern": ".*Dao.*"
}
```

Optional keys (present when `--jsp` / `--recurse` used): `jsp_filter`, `jsp_set`, `jsp_includes`.

## jspmap Internal Flow

```python
# Existing: load call graph
cg_data = json.loads(call_graph_path.read_text())
call_graph = cg_data.get("callees", cg_data)         # already done
callsites = cg_data.get("callsites", {})              # NEW: load from buildcg output
method_lines = cg_data.get("methodLines", {})         # NEW: load from buildcg output

# Per EL action:
# 1. Emit jsp node (key: "jsp:/" + action.jsp)
# 2. If action.el non-empty: emit el_expression node (key: "el:/" + action.jsp + "#" + action.el)
#    + edge: jsp_key → el_key, edge_info: {edge_type: "el_call"}
# 3. For each entry_sig:
#    a. Call calltree.build_graph(entry_sig, call_graph, pat, set(), set(),
#                                 nodes, calls, callsites, method_lines, "")
#    b. Emit edge: el_key → entry_sig (or jsp_key → entry_sig if no EL),
#       edge_info: {edge_type: "method_call"}
```

A new optional `--pattern` CLI flag (default `"."`) is passed as `pat` to `calltree.build_graph()`, giving users the same filtering capability as the standalone `calltree` command.

## calltree.py and frames.py Changes

Both emit `node_type: "java_method"` on every node and `edge_info: {}` on every call edge. This is a breaking schema change — any consumer asserting exact output shape must be updated.

## Deletions

- `python/jspmap_to_dot.py` — removed entirely. Users pipe `jspmap | calltree-to-dot` instead.
- `python/tests/test_jspmap_to_dot.py` — removed with the above.

## Files Affected

| File | Change |
|---|---|
| `python/calltree.py` | Add `node_type: "java_method"` to `_node_entry()`; add `edge_info: {}` to all call dicts in `build_graph()` |
| `python/frames.py` | Add `node_type: "java_method"` to node dicts; add `edge_info: {}` to call dicts |
| `python/jspmap/jspmap.py` | Load `callsites`+`methodLines`; add `--pattern` arg; rewrite `run()` to emit flat schema via calltree graft |
| `python/jspmap_to_dot.py` | **Delete** |
| `python/jspmap/tests/test_jspmap.py` | Rewrite assertions for flat schema output |
| `python/tests/test_calltree.py` | Update assertions: verify `node_type` and `edge_info` present |
| `python/tests/test_frames.py` | Same |
| `README.md` | Update Tool Combinations diagram: jspmap feeds into flat schema consumers |

## What Stays Unchanged

- `calltree.build_graph()` signature — no changes to the function itself
- `jspmap` CLI flags — all existing flags preserved; `--pattern` is additive
- `calltree-print`, `frames-print`, `calltree-to-dot` — no changes needed; they already consume `{nodes, calls}` and ignore unknown fields
- jspmap's JSP parsing, bean resolution, and EL extraction logic
