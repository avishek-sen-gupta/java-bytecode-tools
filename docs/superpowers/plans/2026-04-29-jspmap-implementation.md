# jspmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `jspmap` — a static analysis tool that traces JSP EL action expressions through a Java call graph to DAO methods, producing a machine-queryable JSON semantic map.

**Architecture:** In-process pipeline of pluggable stages: a JSP extractor (BeautifulSoup + character-level EL tokenizer), a bean resolver (Protocol with `JsfBeanResolver` as default), and a BFS chain tracer. The CLI wires these together; new resolvers can be added without touching any existing code.

**Tech Stack:** Python 3.13+, `beautifulsoup4`, `xml.etree.ElementTree` (stdlib), `argparse` (stdlib), `pytest`, `uv`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `python/jspmap/__init__.py` | Package marker |
| Create | `python/jspmap/protocols.py` | `BeanInfo` dataclass + `BeanResolver` Protocol |
| Create | `python/jspmap/jsf_bean_map.py` | `JsfBeanResolver` — parses `faces-config.xml` |
| Create | `python/jspmap/jsp_parser.py` | `ELAction` dataclass, EL tokenizer, DOM walk |
| Create | `python/jspmap/chain_builder.py` | `ChainHop` dataclass, BFS chain builder |
| Create | `python/jspmap/jspmap.py` | CLI entry point, resolver registry, pipeline orchestration |
| Create | `python/jspmap/tests/__init__.py` | Test package marker |
| Create | `python/jspmap/tests/test_jsf_bean_map.py` | Unit tests for `JsfBeanResolver` |
| Create | `python/jspmap/tests/test_jsp_parser.py` | Unit tests for tokenizer, classifier, DOM walk |
| Create | `python/jspmap/tests/test_chain_builder.py` | Unit tests for BFS chain builder |
| Create | `python/jspmap/tests/test_jspmap.py` | Integration test: JSP + config + call graph → JSON |
| Modify | `python/pyproject.toml` | Add `beautifulsoup4` dep + `jspmap` script entry |
| Modify | `run-all-tests.sh` | Widen pytest path to include `jspmap/tests/` |
| Modify | `README.md` | Add `jspmap` to Python tools list |

---

## Task 1: Package scaffold

**Files:**
- Create: `python/jspmap/__init__.py`
- Create: `python/jspmap/tests/__init__.py`
- Modify: `python/pyproject.toml`

- [ ] **Step 1: Create the package directories and markers**

```bash
mkdir -p python/jspmap/tests
touch python/jspmap/__init__.py python/jspmap/tests/__init__.py
```

- [ ] **Step 2: Add `beautifulsoup4` dependency and `jspmap` script entry to `python/pyproject.toml`**

In `python/pyproject.toml`, update `dependencies` and `[project.scripts]`:

```toml
[project]
name = "bytecode-tools"
version = "0.1.0"
description = "Visualization and post-processing for bytecode trace output"
requires-python = ">=3.13"
dependencies = ["beautifulsoup4>=4.12"]

[dependency-groups]
dev = ["black>=25.1", "pytest>=8.0"]

[project.scripts]
ftrace-to-dot = "ftrace_to_dot:main"
ftrace-slice = "ftrace_slice:main"
ftrace-expand-refs = "ftrace_expand_refs:main"
ftrace-semantic = "ftrace_semantic:main"
ftrace-validate = "ftrace_validate:main"
frames-print = "frames_print:main"
jspmap = "jspmap.jspmap:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pyright]
exclude = ["tests", ".venv"]

[tool.hatch.build.targets.wheel]
packages = ["."]
```

- [ ] **Step 3: Install the new dependency**

```bash
cd python && uv sync
```

Expected: `beautifulsoup4` appears in the lock and `.venv`.

- [ ] **Step 4: Create `python/jspmap/protocols.py`**

```python
"""Shared types and plugin protocols for jspmap."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BeanInfo:
    name: str   # logical bean name (e.g. "orderAction")
    fqcn: str   # fully qualified class name
    scope: str  # scope string (request / session / application / none)


class BeanResolver(Protocol):
    def resolve(self, config_path: Path) -> dict[str, BeanInfo]: ...
```

- [ ] **Step 5: Verify the package is importable**

```bash
cd python && uv run python -c "from jspmap.protocols import BeanInfo, BeanResolver; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add python/jspmap/ python/pyproject.toml
git commit -m "feat: scaffold jspmap package — protocols, pyproject entry, uv sync"
```

---

## Task 2: `JsfBeanResolver` — parse `faces-config.xml`

**Files:**
- Create: `python/jspmap/jsf_bean_map.py`
- Create: `python/jspmap/tests/test_jsf_bean_map.py`

### RED

- [ ] **Step 1: Write the failing tests**

Create `python/jspmap/tests/test_jsf_bean_map.py`:

```python
"""Tests for JsfBeanResolver."""

import textwrap
from pathlib import Path

import pytest

from jspmap.jsf_bean_map import JsfBeanResolver
from jspmap.protocols import BeanInfo

FACES_CONFIG_BASIC = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
      <managed-bean>
        <managed-bean-name>userBean</managed-bean-name>
        <managed-bean-class>com.example.web.UserBean</managed-bean-class>
        <managed-bean-scope>request</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

FACES_CONFIG_MISSING_CLASS = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>broken</managed-bean-name>
        <managed-bean-class></managed-bean-class>
        <managed-bean-scope>request</managed-bean-scope>
      </managed-bean>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

FACES_CONFIG_NAMESPACED = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config xmlns="http://java.sun.com/xml/ns/javaee">
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")


@pytest.fixture()
def resolver():
    return JsfBeanResolver()


class TestJsfBeanResolverBasic:
    def test_parses_two_beans(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        result = resolver.resolve(config)
        assert set(result.keys()) == {"orderAction", "userBean"}

    def test_bean_name_correct(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert bean.name == "orderAction"

    def test_bean_fqcn_correct(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert bean.fqcn == "com.example.web.OrderAction"

    def test_bean_scope_correct(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert bean.scope == "session"

    def test_returns_frozen_bean_info(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_BASIC)
        bean = resolver.resolve(config)["orderAction"]
        assert isinstance(bean, BeanInfo)

    def test_skips_bean_with_empty_class(self, resolver, tmp_path, capsys):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_MISSING_CLASS)
        result = resolver.resolve(config)
        assert "broken" not in result
        assert "orderAction" in result
        captured = capsys.readouterr()
        assert "broken" in captured.err

    def test_parses_namespaced_xml(self, resolver, tmp_path):
        config = tmp_path / "faces-config.xml"
        config.write_text(FACES_CONFIG_NAMESPACED)
        result = resolver.resolve(config)
        assert "orderAction" in result
        assert result["orderAction"].fqcn == "com.example.web.OrderAction"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd python && uv run pytest jspmap/tests/test_jsf_bean_map.py -v
```

Expected: `ModuleNotFoundError: No module named 'jspmap.jsf_bean_map'`

### GREEN

- [ ] **Step 3: Implement `python/jspmap/jsf_bean_map.py`**

```python
"""JsfBeanResolver — parses faces-config.xml into a managed-bean registry."""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from jspmap.protocols import BeanInfo


def _local(tag: str) -> str:
    """Strip XML namespace from a tag name."""
    return tag.split("}")[-1] if "}" in tag else tag


class JsfBeanResolver:
    """Implements BeanResolver for JSF faces-config.xml managed-bean registration."""

    def resolve(self, config_path: Path) -> dict[str, BeanInfo]:
        root = ET.parse(config_path).getroot()
        return dict(
            filter(None, (_parse_bean(elem) for elem in root.iter() if _local(elem.tag) == "managed-bean"))
        )


def _child_text(elem: ET.Element, local_name: str) -> str:
    return next(
        ((child.text or "").strip() for child in elem if _local(child.tag) == local_name),
        "",
    )


def _parse_bean(elem: ET.Element) -> tuple[str, BeanInfo] | None:
    name = _child_text(elem, "managed-bean-name")
    fqcn = _child_text(elem, "managed-bean-class")
    scope = _child_text(elem, "managed-bean-scope")
    if not fqcn:
        print(f"Warning: bean '{name}' has no class element, skipping", file=sys.stderr)
        return None
    return name, BeanInfo(name=name, fqcn=fqcn, scope=scope)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd python && uv run pytest jspmap/tests/test_jsf_bean_map.py -v
```

Expected: all tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python/jspmap/jsf_bean_map.py python/jspmap/tests/test_jsf_bean_map.py
git commit -m "feat: add JsfBeanResolver with tests — parses faces-config.xml"
```

---

## Task 3: EL tokenizer in `jsp_parser.py`

The EL tokenizer is a character-level scanner. It handles nested braces and string literals (single and double quote). This task covers only the tokenizer; DOM walk and classification come in Task 4.

**Files:**
- Create: `python/jspmap/jsp_parser.py` (tokenizer only for now)
- Create: `python/jspmap/tests/test_jsp_parser.py` (tokenizer tests only)

### RED

- [ ] **Step 1: Write the failing tokenizer tests**

Create `python/jspmap/tests/test_jsp_parser.py`:

```python
"""Tests for jsp_parser — EL tokenizer, classifier, and DOM walk."""

from jspmap.jsp_parser import tokenize_el


class TestTokenizeEl:
    def test_single_hash_expression(self):
        assert tokenize_el("#{a.b}") == ["#{a.b}"]

    def test_single_dollar_expression(self):
        assert tokenize_el("${a.b}") == ["${a.b}"]

    def test_two_expressions_in_one_string(self):
        result = tokenize_el("#{a.b} and #{c.d}")
        assert result == ["#{a.b}", "#{c.d}"]

    def test_no_el_returns_empty(self):
        assert tokenize_el("plain text") == []

    def test_nested_braces_inside_expression(self):
        # #{map.get('key{1}')} — braces inside single-quoted string do not close the expression
        result = tokenize_el("#{map.get('key{1}')}")
        assert result == ["#{map.get('key{1}')}"]

    def test_double_quoted_string_with_braces(self):
        result = tokenize_el('#{map.get("k{v}")}')
        assert result == ['#{map.get("k{v}")}']

    def test_expression_embedded_in_larger_string(self):
        result = tokenize_el("prefix #{a.b} suffix")
        assert result == ["#{a.b}"]

    def test_adjacent_expressions(self):
        result = tokenize_el("#{a.b}#{c.d}")
        assert result == ["#{a.b}", "#{c.d}"]

    def test_unmatched_brace_not_included(self):
        # A lone # not followed by { should not trigger an expression
        result = tokenize_el("# not an expression")
        assert result == []

    def test_returns_list_not_generator(self):
        result = tokenize_el("#{a.b}")
        assert isinstance(result, list)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd python && uv run pytest jspmap/tests/test_jsp_parser.py::TestTokenizeEl -v
```

Expected: `ImportError: cannot import name 'tokenize_el' from 'jspmap.jsp_parser'`

### GREEN

- [ ] **Step 3: Create `python/jspmap/jsp_parser.py` with `tokenize_el`**

```python
"""Parse JSP/XHTML files and extract EL expressions with source context."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ELAction:
    jsp: str        # relative path from jsps_root
    el: str         # raw expression text, e.g. "#{orderAction.submit}"
    tag: str        # enclosing tag name, or "_text" for text nodes
    attribute: str  # attribute name, or "_text" for text node content
    bean_name: str  # first identifier in the expression
    member: str     # first member access, or "" if none


def tokenize_el(text: str) -> list[str]:
    """Extract all #{...} and ${...} EL expressions from a string.

    Character-level scanner: tracks brace depth, skips braces inside
    single- and double-quoted string literals.
    """
    results = []
    i = 0
    n = len(text)
    while i < n - 1:
        if text[i] in ("#", "$") and text[i + 1] == "{":
            depth = 1
            start = i
            i += 2
            in_single = False
            in_double = False
            while i < n and depth > 0:
                ch = text[i]
                if in_single:
                    if ch == "'":
                        in_single = False
                elif in_double:
                    if ch == '"':
                        in_double = False
                else:
                    if ch == "'":
                        in_single = True
                    elif ch == '"':
                        in_double = True
                    elif ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                i += 1
            if depth == 0:
                results.append(text[start:i])
        else:
            i += 1
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd python && uv run pytest jspmap/tests/test_jsp_parser.py::TestTokenizeEl -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python/jspmap/jsp_parser.py python/jspmap/tests/test_jsp_parser.py
git commit -m "feat: add EL tokenizer with tests — character-level scanner for JSF EL expressions"
```

---

## Task 4: EL classifier + DOM walk in `jsp_parser.py`

**Files:**
- Modify: `python/jspmap/jsp_parser.py` (add `classify_el`, `parse_jsps`)
- Modify: `python/jspmap/tests/test_jsp_parser.py` (add classifier + DOM walk tests)

### RED

- [ ] **Step 1: Add failing tests to `python/jspmap/tests/test_jsp_parser.py`**

Append to the existing test file:

```python
import textwrap
import os
from jspmap.jsp_parser import classify_el, parse_jsps


class TestClassifyEl:
    def test_simple_bean_and_member(self):
        assert classify_el("#{orderAction.submit}") == ("orderAction", "submit")

    def test_no_member_returns_empty_string(self):
        bn, mem = classify_el("#{orderAction}")
        assert bn == "orderAction"
        assert mem == ""

    def test_chained_member_returns_first_only(self):
        bn, mem = classify_el("#{a.b.c}")
        assert bn == "a"
        assert mem == "b"

    def test_dollar_expression(self):
        bn, mem = classify_el("${foo.bar}")
        assert bn == "foo"
        assert mem == "bar"

    def test_arithmetic_expression_returns_empty_bean(self):
        bn, mem = classify_el("#{1 + 2}")
        assert bn == ""
        assert mem == ""

    def test_does_not_mutate_input(self):
        expr = "#{a.b}"
        original = expr[:]
        classify_el(expr)
        assert expr == original


class TestParseJsps:
    def test_extracts_action_attribute(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text(
            '<h:commandButton action="#{orderAction.submit}" />'
        )
        result = parse_jsps(jsp_dir, ["jsp"])
        assert len(result) == 1
        action = result[0]
        assert action.el == "#{orderAction.submit}"
        assert action.tag == "h:commandbutton"  # BeautifulSoup lowercases tag names
        assert action.attribute == "action"
        assert action.bean_name == "orderAction"
        assert action.member == "submit"

    def test_extracts_text_node(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text("<p>#{userBean.name}</p>")
        result = parse_jsps(jsp_dir, ["jsp"])
        text_actions = [a for a in result if a.attribute == "_text"]
        assert len(text_actions) == 1
        assert text_actions[0].bean_name == "userBean"
        assert text_actions[0].member == "name"

    def test_no_el_produces_empty_result(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text("<html><body>Hello world</body></html>")
        result = parse_jsps(jsp_dir, ["jsp"])
        assert result == []

    def test_jsp_path_is_relative_to_root(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        sub = jsp_dir / "pages"
        sub.mkdir(parents=True)
        (sub / "order.jsp").write_text('<h:commandButton action="#{a.b}" />')
        result = parse_jsps(jsp_dir, ["jsp"])
        assert result[0].jsp == os.path.join("pages", "order.jsp")

    def test_multiple_extensions(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "a.jsp").write_text('<f:view action="#{a.m}" />')
        (jsp_dir / "b.xhtml").write_text('<h:form action="#{b.m}" />')
        result = parse_jsps(jsp_dir, ["jsp", "xhtml"])
        bean_names = {a.bean_name for a in result}
        assert "a" in bean_names
        assert "b" in bean_names

    def test_does_not_mutate_input(self, tmp_path):
        jsp_dir = tmp_path / "jsps"
        jsp_dir.mkdir()
        (jsp_dir / "test.jsp").write_text('<h:commandButton action="#{a.b}" />')
        extensions = ["jsp"]
        original = extensions[:]
        parse_jsps(jsp_dir, extensions)
        assert extensions == original
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd python && uv run pytest jspmap/tests/test_jsp_parser.py::TestClassifyEl jspmap/tests/test_jsp_parser.py::TestParseJsps -v
```

Expected: `ImportError: cannot import name 'classify_el' from 'jspmap.jsp_parser'`

### GREEN

- [ ] **Step 3: Add `classify_el` and `parse_jsps` to `python/jspmap/jsp_parser.py`**

Append after `tokenize_el`:

```python
import re
import sys

from bs4 import BeautifulSoup, NavigableString, Tag


_IDENT_RE = re.compile(r"^\w+")


def classify_el(expr: str) -> tuple[str, str]:
    """Parse #{beanName.member} → (bean_name, member).

    Returns ("", "") for expressions that do not start with a simple identifier.
    Returns (bean_name, "") when there is no member access.
    """
    inner = expr[2:-1].strip()
    m = _IDENT_RE.match(inner)
    if not m:
        return ("", "")
    bean = m.group(0)
    rest = inner[len(bean):]
    if not rest.startswith("."):
        return (bean, "")
    after_dot = rest[1:]
    mem_m = _IDENT_RE.match(after_dot)
    return (bean, mem_m.group(0) if mem_m else "")


def _actions_from_value(jsp: str, tag: str, attr: str, value: str) -> list[ELAction]:
    return [
        ELAction(jsp=jsp, el=expr, tag=tag, attribute=attr, bean_name=bn, member=mem)
        for expr in tokenize_el(value)
        for bn, mem in [classify_el(expr)]
        if bn
    ]


def parse_jsps(jsps_root: Path, extensions: list[str]) -> list[ELAction]:
    """Walk jsps_root recursively for files matching extensions. Return all ELActions."""
    return [
        action
        for ext in extensions
        for path in sorted(jsps_root.rglob(f"*.{ext.lstrip('.')}"))
        for action in _parse_file(jsps_root, path)
    ]


def _parse_file(root: Path, path: Path) -> list[ELAction]:
    rel = str(path.relative_to(root))
    try:
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        return [
            action
            for tag in soup.find_all(True)
            for action in _parse_tag(rel, tag)
        ]
    except Exception as exc:
        print(f"Warning: could not parse {path}: {exc}", file=sys.stderr)
        return []


def _parse_tag(jsp: str, tag: Tag) -> list[ELAction]:
    tag_name = tag.name or "_text"
    attr_actions = [
        action
        for attr, val in (tag.attrs or {}).items()
        for action in _actions_from_value(jsp, tag_name, attr, " ".join(val) if isinstance(val, list) else str(val))
    ]
    text_actions = [
        action
        for child in tag.children
        if isinstance(child, NavigableString)
        for action in _actions_from_value(jsp, tag_name, "_text", str(child))
    ]
    return attr_actions + text_actions
```

- [ ] **Step 4: Run all jsp_parser tests**

```bash
cd python && uv run pytest jspmap/tests/test_jsp_parser.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python/jspmap/jsp_parser.py python/jspmap/tests/test_jsp_parser.py
git commit -m "feat: add EL classifier and JSP DOM walk with tests"
```

---

## Task 5: `chain_builder.py` — BFS chain tracer

**Files:**
- Create: `python/jspmap/chain_builder.py`
- Create: `python/jspmap/tests/test_chain_builder.py`

### RED

- [ ] **Step 1: Write the failing tests**

Create `python/jspmap/tests/test_chain_builder.py`:

```python
"""Tests for chain_builder BFS tracer."""

import copy
import re

from jspmap.chain_builder import ChainHop, build_chains

# Helpers — all sigs follow the Soot format <FQCN: returnType method(args)>
DAO_PAT = re.compile(r"com\.example\.dao")
NO_LAYERS: dict[str, re.Pattern] = {}


def _sig(fqcn: str, method: str) -> str:
    return f"<{fqcn}: void {method}()>"


class TestBuildChainsBasic:
    def test_single_hop_entry_is_dao(self):
        # Entry point IS the DAO — one chain of length 1
        cg = {_sig("com.example.dao.Dao", "save"): []}
        chains = build_chains(cg, _sig("com.example.dao.Dao", "save"), DAO_PAT, NO_LAYERS)
        assert len(chains) == 1
        assert chains[0][0].fqcn == "com.example.dao.Dao"

    def test_multi_hop_chain(self):
        entry = _sig("com.example.web.Action", "submit")
        service = _sig("com.example.svc.Service", "process")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [service], service: [dao], dao: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert len(chains) == 1
        assert [h.method for h in chains[0]] == ["submit", "process", "save"]

    def test_no_dao_reached_returns_empty(self):
        entry = _sig("com.example.web.Action", "submit")
        service = _sig("com.example.svc.Service", "process")
        cg = {entry: [service], service: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert chains == []

    def test_cycle_detected_no_chain(self):
        entry = _sig("com.example.web.Action", "a")
        b = _sig("com.example.web.Action", "b")
        cg = {entry: [b], b: [entry]}  # cycle
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert chains == []

    def test_multiple_chains_to_different_daos(self):
        entry = _sig("com.example.web.Action", "submit")
        dao1 = _sig("com.example.dao.Dao1", "save")
        dao2 = _sig("com.example.dao.Dao2", "find")
        cg = {entry: [dao1, dao2], dao1: [], dao2: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert len(chains) == 2
        leaf_methods = {chains[0][-1].method, chains[1][-1].method}
        assert leaf_methods == {"save", "find"}

    def test_max_depth_respected(self):
        # Linear chain longer than max_depth — no chain reaches dao
        sigs = [_sig(f"com.example.svc.S{i}", "m") for i in range(10)]
        dao = _sig("com.example.dao.Dao", "save")
        cg = {sigs[i]: [sigs[i + 1]] for i in range(9)}
        cg[sigs[9]] = [dao]
        cg[dao] = []
        # max_depth=5 means we stop before reaching the dao
        chains = build_chains(cg, sigs[0], DAO_PAT, NO_LAYERS, max_depth=5)
        assert chains == []

    def test_does_not_mutate_call_graph(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        original = copy.deepcopy(cg)
        build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert cg == original


class TestBuildChainsLayerAnnotation:
    def test_layer_assigned_to_hops(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        layers = {
            "web": re.compile(r"com\.example\.web"),
            "dao": re.compile(r"com\.example\.dao"),
        }
        chains = build_chains(cg, entry, DAO_PAT, layers)
        assert chains[0][0].layer == "web"
        assert chains[0][1].layer == "dao"

    def test_no_matching_layer_gives_empty_string(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        # Layer pattern does not match anything
        layers = {"other": re.compile(r"com\.other")}
        chains = build_chains(cg, entry, DAO_PAT, layers)
        assert chains[0][0].layer == ""


class TestChainHopFields:
    def test_hop_fqcn_extracted_correctly(self):
        entry = _sig("com.example.web.Action", "submit")
        dao = _sig("com.example.dao.Dao", "save")
        cg = {entry: [dao], dao: []}
        chains = build_chains(cg, entry, DAO_PAT, NO_LAYERS)
        assert chains[0][0].fqcn == "com.example.web.Action"
        assert chains[0][0].method == "submit"
        assert chains[0][0].signature == entry
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd python && uv run pytest jspmap/tests/test_chain_builder.py -v
```

Expected: `ModuleNotFoundError: No module named 'jspmap.chain_builder'`

### GREEN

- [ ] **Step 3: Implement `python/jspmap/chain_builder.py`**

```python
"""BFS chain builder — finds all call chains from an entry point to DAO leaf nodes."""

import re
from collections import deque
from dataclasses import dataclass


@dataclass(frozen=True)
class ChainHop:
    signature: str  # full Soot method signature
    fqcn: str       # class name extracted from signature
    method: str     # method name extracted from signature
    layer: str      # caller-supplied layer label, or ""


def _fqcn_from_sig(sig: str) -> str:
    """'<com.example.Foo: void bar()>' → 'com.example.Foo'"""
    colon = sig.find(":")
    return sig[1:colon].strip() if colon != -1 else ""


def _method_from_sig(sig: str) -> str:
    """'<com.example.Foo: void bar()>' → 'bar'"""
    colon = sig.find(":")
    if colon == -1:
        return ""
    rest = sig[colon + 1:].strip()
    parts = rest.split()
    if len(parts) < 2:
        return ""
    name_part = parts[1]
    paren = name_part.find("(")
    return name_part[:paren] if paren != -1 else name_part


def _assign_layer(fqcn: str, layer_patterns: dict[str, re.Pattern]) -> str:
    return next(
        (name for name, pat in layer_patterns.items() if pat.search(fqcn)),
        "",
    )


def _make_hop(sig: str, layer_patterns: dict[str, re.Pattern]) -> ChainHop:
    fqcn = _fqcn_from_sig(sig)
    return ChainHop(
        signature=sig,
        fqcn=fqcn,
        method=_method_from_sig(sig),
        layer=_assign_layer(fqcn, layer_patterns),
    )


def build_chains(
    call_graph: dict[str, list[str]],
    entry_signature: str,
    dao_pattern: re.Pattern,
    layer_patterns: dict[str, re.Pattern],
    max_depth: int = 50,
) -> list[list[ChainHop]]:
    """BFS from entry_signature. Returns all paths that terminate at a DAO node.

    A node is a DAO leaf when its FQCN matches dao_pattern.
    Cycles are detected by checking the current path; no chain is recorded.
    """
    initial = _make_hop(entry_signature, layer_patterns)
    queue: deque[tuple[str, tuple[ChainHop, ...]]] = deque(
        [(entry_signature, (initial,))]
    )
    chains: list[list[ChainHop]] = []

    while queue:
        sig, path = queue.popleft()
        if dao_pattern.search(_fqcn_from_sig(sig)):
            chains.append(list(path))
            continue
        if len(path) >= max_depth:
            continue
        path_sigs = frozenset(h.signature for h in path)
        queue.extend(
            (callee, path + (_make_hop(callee, layer_patterns),))
            for callee in call_graph.get(sig, [])
            if callee not in path_sigs
        )

    return chains
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd python && uv run pytest jspmap/tests/test_chain_builder.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python/jspmap/chain_builder.py python/jspmap/tests/test_chain_builder.py
git commit -m "feat: add BFS chain builder with tests — traces entry points to DAO leaves"
```

---

## Task 6: `jspmap.py` CLI — orchestration and integration test

**Files:**
- Create: `python/jspmap/jspmap.py`
- Create: `python/jspmap/tests/test_jspmap.py`

### RED

- [ ] **Step 1: Write the integration test**

Create `python/jspmap/tests/test_jspmap.py`:

```python
"""Integration tests for jspmap CLI orchestration."""

import json
import sys
import textwrap

import pytest

from jspmap.jspmap import run


# Synthetic fixtures — no strings from any real application

FACES_CONFIG = textwrap.dedent("""\
    <?xml version="1.0"?>
    <faces-config>
      <managed-bean>
        <managed-bean-name>orderAction</managed-bean-name>
        <managed-bean-class>com.example.web.OrderAction</managed-bean-class>
        <managed-bean-scope>session</managed-bean-scope>
      </managed-bean>
    </faces-config>
""")

CALL_GRAPH = {
    "<com.example.web.OrderAction: void submit()>": [
        "<com.example.svc.OrderService: void place()>"
    ],
    "<com.example.svc.OrderService: void place()>": [
        "<com.example.dao.JdbcDao: void save()>"
    ],
    "<com.example.dao.JdbcDao: void save()>": [],
}

LAYERS = {
    "web": r"com\.example\.web",
    "service": r"com\.example\.svc",
    "dao": r"com\.example\.dao",
}


@pytest.fixture()
def workspace(tmp_path):
    jsp_dir = tmp_path / "jsps"
    jsp_dir.mkdir()
    (jsp_dir / "order.jsp").write_text(
        '<h:commandButton action="#{orderAction.submit}" />'
    )
    faces = tmp_path / "faces-config.xml"
    faces.write_text(FACES_CONFIG)
    cg = tmp_path / "callgraph.json"
    cg.write_text(json.dumps(CALL_GRAPH))
    layers_file = tmp_path / "layers.json"
    layers_file.write_text(json.dumps(LAYERS))
    return {
        "jsp_dir": jsp_dir,
        "faces": faces,
        "cg": cg,
        "layers": layers_file,
        "tmp": tmp_path,
    }


class TestRunEndToEnd:
    def test_output_has_meta(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        assert result["meta"]["dao_pattern"] == r"com\.example\.dao"

    def test_output_has_one_action(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        assert len(result["actions"]) == 1

    def test_action_el_and_bean_resolved(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        action = result["actions"][0]
        assert action["el"] == "#{orderAction.submit}"
        assert action["bean"]["class"] == "com.example.web.OrderAction"
        assert action["bean"]["scope"] == "session"

    def test_chain_ends_at_dao(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        chain = result["actions"][0]["chains"][0]
        assert chain[-1]["class"] == "com.example.dao.JdbcDao"
        assert chain[-1]["method"] == "save"

    def test_chain_has_all_hops(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        chain = result["actions"][0]["chains"][0]
        assert len(chain) == 3

    def test_layers_flag_annotates_hops(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
            layers_path=workspace["layers"],
        )
        chain = result["actions"][0]["chains"][0]
        layers = [h["layer"] for h in chain]
        assert layers == ["web", "service", "dao"]

    def test_unresolved_bean_gives_empty_chains(self, workspace, tmp_path):
        # JSP references a bean not in faces-config.xml
        jsp_dir = tmp_path / "j2"
        jsp_dir.mkdir()
        (jsp_dir / "page.jsp").write_text('<h:commandButton action="#{unknownBean.go}" />')
        result = run(
            jsps=jsp_dir,
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        action = result["actions"][0]
        assert action["bean"] is None
        assert action["chains"] == []

    def test_output_is_json_serialisable(self, workspace):
        result = run(
            jsps=workspace["jsp_dir"],
            faces_config=workspace["faces"],
            call_graph_path=workspace["cg"],
            dao_pattern=r"com\.example\.dao",
        )
        serialised = json.dumps(result)
        assert json.loads(serialised) == result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd python && uv run pytest jspmap/tests/test_jspmap.py -v
```

Expected: `ModuleNotFoundError: No module named 'jspmap.jspmap'`

### GREEN

- [ ] **Step 3: Implement `python/jspmap/jspmap.py`**

```python
"""jspmap CLI — trace JSP EL actions through a call graph to DAO methods."""

import argparse
import json
import re
import sys
from pathlib import Path

from jspmap.chain_builder import ChainHop, build_chains
from jspmap.jsf_bean_map import JsfBeanResolver
from jspmap.jsp_parser import ELAction, parse_jsps
from jspmap.protocols import BeanInfo, BeanResolver

# Registry of available resolver names → resolver classes.
# Add new resolvers here; no other file needs to change.
_RESOLVERS: dict[str, type[BeanResolver]] = {
    "jsf": JsfBeanResolver,
}


def _load_layer_patterns(path: Path | None) -> dict[str, re.Pattern]:
    if path is None:
        return {}
    return {name: re.compile(pat) for name, pat in json.loads(path.read_text()).items()}


def _hop_to_dict(hop: ChainHop) -> dict:
    return {
        "layer": hop.layer,
        "class": hop.fqcn,
        "method": hop.method,
        "signature": hop.signature,
    }


def _bean_to_dict(bean: BeanInfo | None) -> dict | None:
    if bean is None:
        return None
    return {"name": bean.name, "class": bean.fqcn, "scope": bean.scope}


def _entry_sigs_for(action: ELAction, call_graph: dict[str, list[str]], fqcn: str) -> list[str]:
    prefix = f"<{fqcn}:"
    return [
        sig for sig in call_graph
        if sig.startswith(prefix) and f" {action.member}(" in sig
    ]


def _chains_for_action(
    action: ELAction,
    bean_map: dict[str, BeanInfo],
    call_graph: dict[str, list[str]],
    dao_pattern: re.Pattern,
    layer_patterns: dict[str, re.Pattern],
    max_depth: int,
) -> list[dict]:
    bean = bean_map.get(action.bean_name)
    if bean is None or not action.member:
        return []
    return [
        [_hop_to_dict(h) for h in chain]
        for sig in _entry_sigs_for(action, call_graph, bean.fqcn)
        for chain in build_chains(call_graph, sig, dao_pattern, layer_patterns, max_depth)
    ]


def _action_to_dict(
    action: ELAction,
    bean_map: dict[str, BeanInfo],
    call_graph: dict[str, list[str]],
    dao_pattern: re.Pattern,
    layer_patterns: dict[str, re.Pattern],
    max_depth: int,
) -> dict:
    bean = bean_map.get(action.bean_name)
    entry_sigs = _entry_sigs_for(action, call_graph, bean.fqcn) if bean and action.member else []
    return {
        "jsp": action.jsp,
        "el": action.el,
        "el_context": {"tag": action.tag, "attribute": action.attribute},
        "bean": _bean_to_dict(bean),
        "entry_signature": entry_sigs[0] if entry_sigs else None,
        "chains": _chains_for_action(
            action, bean_map, call_graph, dao_pattern, layer_patterns, max_depth
        ),
    }


def run(
    jsps: Path,
    faces_config: Path,
    call_graph_path: Path,
    dao_pattern: str,
    resolver_name: str = "jsf",
    layers_path: Path | None = None,
    max_depth: int = 50,
    extensions: list[str] | None = None,
) -> dict:
    """Core pipeline. Returns the semantic map as a plain dict (JSON-serialisable)."""
    exts = extensions or ["jsp", "jspf", "xhtml"]
    dao_pat = re.compile(dao_pattern)
    layer_pats = _load_layer_patterns(layers_path)

    resolver_cls = _RESOLVERS.get(resolver_name)
    if resolver_cls is None:
        raise ValueError(f"Unknown resolver '{resolver_name}'. Known: {list(_RESOLVERS)}")

    el_actions = parse_jsps(jsps, exts)
    bean_map = resolver_cls().resolve(faces_config)
    call_graph: dict[str, list[str]] = json.loads(call_graph_path.read_text())

    return {
        "meta": {
            "jsps_root": str(jsps),
            "faces_config": str(faces_config),
            "call_graph": str(call_graph_path),
            "dao_pattern": dao_pattern,
        },
        "actions": [
            _action_to_dict(action, bean_map, call_graph, dao_pat, layer_pats, max_depth)
            for action in el_actions
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Trace JSP EL actions through a call graph to DAO methods."
    )
    parser.add_argument("--jsps", required=True, type=Path, help="Root directory of JSP files")
    parser.add_argument("--faces-config", required=True, type=Path, dest="faces_config",
                        help="Path to the resolver config file (e.g. faces-config.xml)")
    parser.add_argument("--call-graph", required=True, type=Path, dest="call_graph",
                        help="Call graph JSON from buildcg")
    parser.add_argument("--dao-pattern", required=True, dest="dao_pattern",
                        help="Regex matched against FQCN to identify DAO leaf nodes")
    parser.add_argument("--resolver", default="jsf",
                        help=f"Bean resolver to use (default: jsf; available: {list(_RESOLVERS)})")
    parser.add_argument("--layers", type=Path,
                        help="JSON file mapping layer name → FQCN regex")
    parser.add_argument("--max-depth", type=int, default=50, dest="max_depth",
                        help="BFS depth cap (default: 50)")
    parser.add_argument("--extensions", default="jsp,jspf,xhtml",
                        help="Comma-separated file extensions (default: jsp,jspf,xhtml)")
    parser.add_argument("--output", type=Path, help="Output file (default: stdout)")
    args = parser.parse_args()

    exts = [e.strip() for e in args.extensions.split(",")]
    result = run(
        jsps=args.jsps,
        faces_config=args.faces_config,
        call_graph_path=args.call_graph,
        dao_pattern=args.dao_pattern,
        resolver_name=args.resolver,
        layers_path=args.layers,
        max_depth=args.max_depth,
        extensions=exts,
    )

    out_json = json.dumps(result, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out_json)
        print(f"Wrote semantic map to {args.output}", file=sys.stderr)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the integration tests**

```bash
cd python && uv run pytest jspmap/tests/test_jspmap.py -v
```

Expected: all `PASSED`

- [ ] **Step 5: Commit**

```bash
git add python/jspmap/jspmap.py python/jspmap/tests/test_jspmap.py
git commit -m "feat: add jspmap CLI orchestration with integration tests"
```

---

## Task 7: Wire test runner, smoke test, and docs

**Files:**
- Modify: `run-all-tests.sh`
- Modify: `README.md`
- Modify: `CHEATSHEET.md`

- [ ] **Step 1: Update `run-all-tests.sh` to discover jspmap tests**

Change the Python unit test line from:

```bash
if (cd "$ROOT/python" && python3 -m pytest tests/ -q); then
```

To:

```bash
if (cd "$ROOT/python" && python3 -m pytest tests/ jspmap/tests/ -q); then
```

- [ ] **Step 2: Run the full test suite to verify nothing is broken**

```bash
bash run-all-tests.sh
```

Expected: all three suites (`Java`, `Python`, `E2E`) report `PASSED`

- [ ] **Step 3: Smoke test the CLI end-to-end**

```bash
cd python && uv run jspmap \
  --jsps ../test-fixtures/src \
  --faces-config /dev/null \
  --call-graph /dev/null \
  --dao-pattern "nonexistent" \
  --output /tmp/jspmap-smoke.json 2>&1 || true
# /dev/null will cause a parse error — we just want to confirm the CLI entry point works
uv run jspmap --help
```

Expected: `--help` prints the argument reference without error.

- [ ] **Step 4: Add `jspmap` to `README.md`**

In `README.md`, find the "Key Python commands" list and add:

```markdown
- `jspmap`: map JSP EL actions through call graph to DAO methods; outputs JSON semantic map
```

In the `python/` directory tree listing, add:

```
│   ├── jspmap/              jspmap package — JSP-to-DAO semantic map tool
│   │   ├── protocols.py     BeanInfo + BeanResolver plugin protocol
│   │   ├── jsf_bean_map.py  JsfBeanResolver — reads faces-config.xml
│   │   ├── jsp_parser.py    EL tokenizer, DOM walk, ELAction
│   │   ├── chain_builder.py BFS chain builder, ChainHop
│   │   └── jspmap.py        CLI entry point + resolver registry
```

- [ ] **Step 5: Add `jspmap` section to `CHEATSHEET.md`**

Add after the `frames-print` section:

```markdown
### `jspmap` — JSP-to-DAO semantic map

```bash
$UV jspmap \
  --jsps path/to/jsps \
  --faces-config path/to/faces-config.xml \
  --call-graph callgraph.json \
  --dao-pattern "<dao-fqcn-regex>" \
  --layers layers.json \
  --output semantic-map.json
```

| Option | Required | Description |
|--------|----------|-------------|
| `--jsps <dir>` | Yes | Root directory to walk for JSP files |
| `--faces-config <file>` | Yes | Resolver config file (e.g. faces-config.xml for `--resolver jsf`) |
| `--call-graph <file>` | Yes | Call graph JSON from `buildcg` |
| `--dao-pattern <regex>` | Yes | Regex matched against FQCN to identify DAO leaf nodes |
| `--resolver <name>` | No | Bean resolver (default: `jsf`) |
| `--layers <file>` | No | JSON mapping layer name → FQCN regex |
| `--max-depth <N>` | No | BFS depth cap (default: 50) |
| `--extensions <list>` | No | Comma-separated extensions (default: `jsp,jspf,xhtml`) |
| `--output <file>` | No | Output file (default: stdout) |

**`--layers` file format:**
```json
{
  "action":  "<regex matching action class FQCNs>",
  "service": "<regex matching service FQCNs>",
  "dao":     "<regex matching DAO FQCNs>"
}
```
```

- [ ] **Step 6: Commit**

```bash
git add run-all-tests.sh README.md CHEATSHEET.md
git commit -m "docs: add jspmap to README and CHEATSHEET; widen pytest discovery"
```

---

## Verification Checklist

After all tasks complete, run:

```bash
# Full test suite
bash run-all-tests.sh

# CLI help smoke test
cd python && uv run jspmap --help

# Quick unit pass
cd python && uv run pytest jspmap/tests/ -v
```

All expected to pass cleanly.
