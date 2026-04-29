# Design: jspmap — JSP-to-DAO Semantic Map

## Goal

Build a static analysis tool that traces all interaction paths from JSP UI actions through
the Java call graph to DAO methods, producing a machine-queryable semantic map of the full
call chain at every layer. Output is a JSON artifact; rendering and aggregation are out of
scope for this iteration.

## Scope and Constraints

- Input: JSP source files, a JSF `faces-config.xml`, a pre-built call graph JSON (from `buildcg`)
- Output: a single JSON file (the semantic map)
- Language: Python, living in `java-bytecode-tools/python/jspmap/`
- Zero strings, class names, package names, path fragments, or patterns specific to any
  target application in source code, comments, or documentation
- All application-specific values (DAO pattern, layer patterns, config paths) are supplied
  by the caller at runtime

## Architecture

Three focused modules plus a CLI entry point:

```
python/jspmap/
    __init__.py
    jsp_parser.py      — parse JSP files, extract EL expressions with source context
    jsf_bean_map.py    — parse faces-config.xml, build bean-name → FQCN + scope map
    chain_builder.py   — BFS over call graph from action entry points, enumerate full chains
    jspmap.py          — CLI entry point: orchestrate, assemble semantic map, write JSON
```

### Data flow

```
JSP files         ──► jsp_parser     ──► List[ELAction]
faces-config.xml  ──► jsf_bean_map   ──► Dict[str, BeanInfo]
callgraph.json    ──►                    (loaded directly in chain_builder)
                                               │
                                         chain_builder
                                               │
                                         SemanticMap (JSON)
```

## Module Designs

### `jsp_parser.py`

**Input**: root directory of JSP files (walked recursively), file extensions to include
(default: `.jsp`, `.jspf`, `.xhtml`)

**Parsing strategy**:
- Parse each file with BeautifulSoup (`html.parser`) to obtain a DOM
- Walk all tag attributes and text nodes
- For each string value, run an EL tokenizer to extract `#{...}` and `${...}` expressions
- The EL tokenizer is a character-level scanner (not regex): tracks nesting depth, handles
  string literals with single and double quotes, emits complete balanced expressions

**EL tokenizer behaviour**:
- Recognises `#{` and `${` as expression openers
- Tracks brace depth; closes at the matching `}`
- Skips `{` / `}` inside quoted string literals
- Returns the raw expression text and its position in the source string

**EL expression classification**:
- Parse the first identifier and the first `.member` access from each expression:
  `#{beanName.methodOrProperty}` → `(bean_name="beanName", member="methodOrProperty")`
- Expressions that do not follow this pattern (e.g. arithmetic, boolean, map literals) are
  recorded with `member=None` — they are retained in the output but produce no chains

**Output per file**:
```python
@dataclass(frozen=True)
class ELAction:
    jsp: str            # relative path from jsps_root
    el: str             # raw expression text, e.g. "#{orderAction.submit}"
    tag: str            # enclosing tag name, e.g. "h:commandButton"
    attribute: str      # attribute name, e.g. "action"  ("_text" for text nodes)
    bean_name: str      # first identifier, e.g. "orderAction"
    member: str | None  # first member access, or None
```

### `jsf_bean_map.py`

**Input**: path to `faces-config.xml`

**Parsing**: `xml.etree.ElementTree` — standard library, no extra dependencies

**Output**:
```python
@dataclass(frozen=True)
class BeanInfo:
    name: str       # managed-bean-name
    fqcn: str       # managed-bean-class
    scope: str      # managed-bean-scope (request / session / application / none)
```

Returns `Dict[str, BeanInfo]` keyed by bean name.

Beans whose class element is empty or missing are skipped with a warning to stderr.

### `chain_builder.py`

**Input**:
- `call_graph: Dict[str, List[str]]` — loaded from JSON, signature → callees
- `entry_signature: str` — full method signature to start BFS from
- `dao_pattern: str` — compiled regex; a callee whose class name matches is a leaf
- `max_depth: int` — cycle / depth guard (default: 50)

**Algorithm**: BFS from `entry_signature`. At each node:
- If the class of the current signature matches `dao_pattern`, record the current path as a
  complete chain and do not recurse further
- If a signature is already in the current path, treat as a cycle and stop (no chain recorded)
- If depth exceeds `max_depth`, stop

**Output**: `List[List[ChainHop]]`

```python
@dataclass(frozen=True)
class ChainHop:
    signature: str   # full method signature
    fqcn: str        # class name extracted from signature
    method: str      # method name extracted from signature
    layer: str       # caller-supplied label, or "" if no layer config provided
```

`layer` is assigned by the caller (in `jspmap.py`) by matching `fqcn` against the
user-supplied layer pattern map. `chain_builder` itself has no layer knowledge.

### `jspmap.py` (CLI)

**Flags**:

| Flag | Required | Description |
|------|----------|-------------|
| `--jsps <dir>` | Yes | Root directory to walk for JSP files |
| `--faces-config <file>` | Yes | Path to `faces-config.xml` |
| `--call-graph <file>` | Yes | Path to call graph JSON from `buildcg` |
| `--dao-pattern <regex>` | Yes | Regex matched against FQCN to identify DAO leaf nodes |
| `--layers <file>` | No | JSON file mapping layer name → FQCN regex (see below) |
| `--max-depth <N>` | No | BFS depth cap (default: 50) |
| `--extensions <list>` | No | Comma-separated file extensions (default: `jsp,jspf,xhtml`) |
| `--output <file>` | No | Output file (default: stdout) |

**`--layers` file format**:
```json
{
  "action":  "<regex matching action bean FQCNs>",
  "service": "<regex matching service FQCNs>",
  "dao":     "<regex matching DAO FQCNs>"
}
```
Layer names are arbitrary strings defined by the caller. If `--layers` is omitted, `layer`
is set to `""` for all hops.

**Orchestration**:
1. Parse JSP files → `List[ELAction]`
2. Parse faces-config.xml → `Dict[str, BeanInfo]`
3. Load call graph JSON
4. Load layer patterns (if `--layers` supplied)
5. For each `ELAction`:
   - Resolve `bean_name` → `BeanInfo`; if not found, record action with `bean: null, chains: []`
   - Find all call graph keys whose class and method match `(BeanInfo.fqcn, ELAction.member)`
   - For each matching entry signature, run `chain_builder.build_chains`
   - Annotate each hop with `layer` from pattern map
6. Assemble `SemanticMap` and serialise to JSON

**Unresolved actions** (bean not in faces-config.xml, or member is None) are included in
output with empty chains — nothing is silently dropped.

## Output JSON Shape

```json
{
  "meta": {
    "jsps_root": "<supplied path>",
    "faces_config": "<supplied path>",
    "call_graph": "<supplied path>",
    "dao_pattern": "<supplied regex>"
  },
  "actions": [
    {
      "jsp": "pages/checkout/order.jsp",
      "el": "#{orderAction.submit}",
      "el_context": { "tag": "h:commandButton", "attribute": "action" },
      "bean": {
        "name": "orderAction",
        "class": "com.example.app.web.OrderAction",
        "scope": "session"
      },
      "entry_signature": "<com.example.app.web.OrderAction: void submit()>",
      "chains": [
        [
          { "layer": "action",  "class": "com.example.app.web.OrderAction",            "method": "submit",      "signature": "..." },
          { "layer": "service", "class": "com.example.app.service.OrderServiceImpl",   "method": "placeOrder",  "signature": "..." },
          { "layer": "dao",     "class": "com.example.app.dao.JdbcOrderRepository",    "method": "save",        "signature": "..." }
        ]
      ]
    },
    {
      "jsp": "pages/checkout/order.jsp",
      "el": "#{orderAction.currentUser.name}",
      "el_context": { "tag": "_text", "attribute": "_text" },
      "bean": {
        "name": "orderAction",
        "class": "com.example.app.web.OrderAction",
        "scope": "session"
      },
      "entry_signature": null,
      "chains": []
    }
  ]
}
```

## Prerequisites

The call graph must be built from a classpath that includes both web module classes
(where action beans live) and service/DAO module classes. The tool does not build the call
graph; the caller is responsible for supplying an up-to-date `callgraph.json`.

## Testing

All test fixtures are synthetic — no strings from any real target application.

**Unit tests** (pytest, in `python/jspmap/tests/`):

- `test_jsp_parser.py`
  - EL tokenizer handles nested braces, single-quoted strings, double-quoted strings
  - EL tokenizer ignores `${...}` in attribute values correctly
  - `bean_name` and `member` correctly split from simple `#{a.b}` expressions
  - Expressions without member access (`#{a}`) produce `member=None`
  - DOM walk extracts expressions from tag attributes and text nodes
  - Non-JSP content (plain HTML, no EL) produces empty result

- `test_jsf_bean_map.py`
  - Parses standard managed-bean entries correctly
  - Beans with missing class element are skipped
  - Scope values are preserved as-is

- `test_chain_builder.py`
  - Single-hop chain (action calls DAO directly)
  - Multi-hop chain (action → service → DAO)
  - Cycle detected and not recorded
  - Multiple chains when multiple paths reach different DAOs
  - `max_depth` cap respected
  - No match for `dao_pattern` → empty chains
  - Does not mutate input call graph

- `test_jspmap.py` (integration, uses synthetic fixture JSPs + faces-config.xml)
  - End-to-end: JSP file + faces-config.xml + call graph → expected JSON shape
  - Unresolved bean name produces `bean: null, chains: []`
  - `--layers` flag annotates hops with correct layer names
  - Output is valid JSON

## Out of Scope (this iteration)

- DOT / SVG rendering
- Aggregation views (by JSP, by DAO, by layer)
- Incremental / cached map updates
- Struts, Spring MVC, or other web framework support — JSF faces-config.xml only

## Extensibility Note

The only framework-specific component is `jsf_bean_map.py`, which resolves bean names to FQCNs via `faces-config.xml`. This covers JSF 1.x apps using pure XML managed bean registration. Apps using CDI annotations (`@Named`), Spring annotations (`@Component`, `@Controller`), or Struts action mappings would need a different resolver module. The natural extension point is to make bean resolution a pluggable interface — `jsf_bean_map` becomes one implementation, others can be added without touching `chain_builder` or `jspmap.py`.
