# Java Bytecode Tools — Agent Instructions

## Project Context

- **Languages:** Java 21+ (SootUp bytecode analysis), Python 3.13+ (visualization pipeline)
- **Build:** Maven (Java), uv (Python)
- **Test frameworks:** JUnit (Java), pytest (Python), bash E2E (`test-fixtures/run-e2e.sh`)
- **Formatter:** Black (Python), google-java-format (Java)
- **Pre-commit hooks:** Black, google-java-format, Talisman (secret detection), E2E tests
- **Specs (immutable):** `docs/superpowers/specs/` and `docs/superpowers/plans/` — never modify these. Newer specs supersede older ones by convention.

## Workflow

### Phases (mandatory, in order)

Every non-trivial task goes through these phases. Do not skip. Do not start implementing before completing brainstorm.

1. **Brainstorm** — Always invoke the `superpowers:brainstorming` skill first. Read the relevant code. Check how the existing system handles similar cases. Identify at least two approaches and their trade-offs. Ask: "does the system already have infrastructure for this?"
2. **Plan** — Choose an approach. For features spanning multiple modules, identify independently-committable units and their order. Use the `superpowers:writing-plans` skill for multi-step tasks.
3. **Test first** — Write failing tests that define the expected behavior. No implementation code until at least one test exists.
4. **Implement** — Write the minimum code to make the tests pass.
5. **Self-review** — Before committing, review your own diff (`git diff`). Check against the Design Principles and Programming Patterns sections below. Look for: workaround guards, mutation in loops, missing test coverage, weak assertions, stale docs.
6. **Verify** — Run the full test suite. All checks must pass.
7. **Commit** — One logical unit per commit.

When asked to audit or show issues, only report findings — do not fix unless explicitly asked.

### Complexity classification

Classify before starting. This determines how much ceremony is needed.

- **Light** (< 50 lines, single file, no new abstractions) — brief brainstorm.
- **Standard** (50-300 lines, 2-5 files, follows existing patterns) — brainstorm identifies the pattern being followed.
- **Heavy** (300+ lines, new abstractions, multiple subsystems) — brainstorm must produce a written design with trade-offs before any code. Break into independently-committable units. Do not attempt in a single pass.

### Commits and state

- One logical unit per commit. Each commit must have its own tests.
- Push to `main` unless otherwise instructed.
- Update README and other living docs if the diff changes public behavior, adds features, or modifies architecture. This is part of the commit, not a follow-up.
- Leave the working directory clean. No uncommitted files.
- Prefer a committed partial result over an uncommitted complete attempt. If a session may end, commit what's done with a `WIP:` prefix.

## Interaction Style

- When interrupted or cancelled, immediately proceed with the new instruction. No clarifying questions — treat interruptions as implicit redirects.
- **Brainstorm collaboratively.** Present options and trade-offs to the user and actively incorporate their input before proceeding. Do not pick an approach and start implementing without discussion.
- **Stop and consult when patching.** If an implementation requires more than one corrective patch (fix-on-fix), stop. The design is wrong. Re-brainstorm the approach with the user before adding more patches.

## Design Principles

- **Use existing infrastructure before adding new abstractions.** Ask: "does the system already have something that solves this?" The answer is usually yes.
- **Start from the simplest possible mechanism.** Begin with minimal intervention. Add complexity only when proven insufficient.
- **No speculative code without tests.** Every code path must have a test that exercises it.
- **Stay consistent with established patterns.** When the codebase has a way of doing something, use it.
- **Never mask bugs with workaround guards.** Don't add `is not None` checks to make tests pass. Fix the root cause.
- **Pass decisions through data, don't re-derive downstream.** If a decision was made upstream, attach it to the data. Don't re-detect via fragile lookups.

## Programming Patterns

### Code style

- **Functional programming style.** This is non-negotiable.
  - Avoid `for` loops with mutations — use comprehensions, `map`, `filter`, `reduce`.
  - **No nested for...if loops** — use comprehensions, `filter`, `itertools` instead.
  - Small, composable, pure functions. Each function does one thing, returns a value.
  - Prefer early return. Guard clauses at top of functions; happy path outside conditions.
  - No module-level mutable state or globals. Dependency injection for all external dependencies.
- Constants instead of magic strings and numbers.
- Enums (`StrEnum`) for fixed string sets, not raw strings.
- Logging, not `print` statements (except CLI `main()` entry points).

### Types and values

- **No `None` checks. No `Optional` in type hints. No `X | None`.** Use null object pattern: empty collections `{}`, `[]`, empty strings `""`, `False`.
- **No defensive `.get()` with implicit `None` fallback.** Always provide a concrete default: `dict.get(key, "")`, `dict.get(key, [])`, `dict.get(key, False)`.
- **Immutable data by default.** Prefer `frozenset` over `set`, frozen dataclasses. Mutable state only in imperative shell (I/O, CLI entry points).
- Strong typing via `TypedDict` and `StrEnum` at API boundaries. No bare dicts at public interfaces.
- Domain-appropriate wrapping types for data crossing function boundaries.

### Testing

- **TDD is mandatory.** Write tests first, see them fail, then implement. No exceptions.
- Every new function or pass gets tests before implementation code.
- Include immutability tests (`test_does_not_mutate_input`) for pure functions that take mutable arguments.
- Concrete assertions — no `assert result is not None`. Assert specific values, shapes, fields.

### Architecture

- Functional core, imperative shell.
- Mutable state is permitted only in the imperative shell (I/O, file writes, subprocess calls). The functional core receives and returns immutable values.

## Talisman (Secret Detection)

- If Talisman detects a potential secret, **stop** and prompt for guidance before updating `.talismanrc`.
- Don't overwrite existing `.talismanrc` entries — add at the end.

## Code Search and Analysis Tools

### code-review-graph (knowledge graph)

Use the code-review-graph MCP tools before scanning files manually for codebase understanding:

- `semantic_search_nodes_tool` — find classes, functions, or types by name or keyword
- `query_graph_tool` — explore relationships: `callers_of`, `callees_of`, `imports_of`, `children_of`
- `get_impact_radius_tool` — understand blast radius before making changes

Fall back to grep/glob/read only when the graph doesn't cover what you need.
