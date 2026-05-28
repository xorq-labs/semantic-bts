---
description: Compose and run xorq catalog entries. Use when the user wants to combine a source with transforms, apply inline code, run expressions, or build scripts into artifacts.
---

# Composer — Compose, Run, and Build Expressions

Compose existing catalog entries, run them, and optionally catalog the results.

## Do NOT shell out

The xorq extension is authoritative — prefer registered tools over `bash`.

- Do NOT run `xorq catalog ...` directly. Use `catalog_list`, `catalog_run`,
  `catalog_compose`, `catalog_schema`, `catalog_add`, etc.
- Do NOT write standalone Python scripts to query or inspect catalog entries.
  Use the tools (`catalog_run`, `bsl_query`, `bsl_describe`).
- Only drop to bash/python for **build scripts** that define an `expr` variable
  for `xorq_build`.

### Common API mistakes (avoid these)

- `Catalog.from_path()` does NOT exist → use `Catalog.from_repo_path()`
- `Catalog(path_string)` does NOT work → constructor takes a `CatalogBackend`
- `SemanticModel.from_tagged()` does NOT exist → use `boring_semantic_layer.from_tagged()` (module-level)

## When NOT to use composer

If the user's question can be answered by querying an **existing BSL
semantic model** (an `ExprBuilder` entry whose `.ls.builder` returns a
`SemanticModel`) with its declared dimensions and measures, **use the
`builder` skill instead**. Composer's inline `-c` code can technically
re-implement an aggregate, but doing so bypasses the semantic layer and
duplicates measure definitions that already exist. Reach for composer when
you need a per-row filter/mutate/select on a `Source` or `Composed` entry
that the semantic model doesn't cover.

## Quick start: the `catalog_run` tool

The fastest way to inspect a cataloged entry — call **`catalog_run`** with `name` (the entry name or alias). Pass `format` (`csv`, `json`, or `parquet`) and `limit` to keep output manageable. This does not catalog the result.

For inline transforms or composing two entries on the fly, use **`catalog_compose`** with `dry_run: true` (preview) or `dry_run: false` + `alias` (catalog the composed result).

## Composing and cataloging

To compose AND add to the catalog, call **`catalog_compose`** with:
- `source` — name/alias of a `Source` or `Composed` entry
- `transforms` — optional list of `UnboundExpr` entry names
- `code` — optional single-expression inline ibis code applied to the `source` variable
- `alias` — alias for the new composed entry
- `dry_run: true` to preview without persisting

**IMPORTANT:** Only entries with `kind=UnboundExpr` can be used as transform entries. You CANNOT compose two `Source` entries together (e.g., to join them). To join two sources, use inline code (`-c`) on one source and reference the other via Python:

**Joining two source entries (use a build script — NOT inline code):**

Inline `-c` code must be a **single expression** (no imports, no assignments). For joins or anything requiring multiple statements, write a build script instead:

```python
# join_sources.py
import xorq.api as xo
from xorq.catalog.catalog import Catalog

con = xo.connect()  # shared connection — required for joins
cat = Catalog.from_default()
source1 = cat.load("entry1", con=con)
source2 = cat.load("entry2", con=con)

expr = source1.join(source2, "join_key").select("col1", "col2", "col3")
```

Then call **`xorq_build`** (`script: join_sources.py`) and **`catalog_add`** (`build_path`, `alias`).

**Source + transforms (unbound_expr only):** `catalog_compose` with `source` and `transforms`.

**Source + inline code (most flexible — try this first):** `catalog_compose` with `source` and `code` (e.g. `"source.filter(source.amount > 15)"`). The inline code receives the expression as the `source` variable.

Inline-code rules:
- **Single expression, one line** — no imports, no assignments, no multiline code.
- **No bitwise ops** — `&`, `|`, `~` are rejected by the parser. Chain `.filter()` calls instead: `source.filter(source.x.notnull()).filter(source.x > 0)`.
- **No deferred `_`** — `_` is not in scope; reference columns via `source.<col>`.
- **`xo` IS in scope** — so `xo.window(...)`, `xo.literal(...)`, etc. work inline. Window aggregates fit on one line:
  ```
  source.mutate(med=source.x.median().over(xo.window(group_by="species"))).filter(source.x.notnull())
  ```
- **Lambdas work in `.filter(...)`** — useful for referencing columns added by a preceding `.mutate(...)` (which `source.<col>` cannot see):
  ```
  source.mutate(med=source.x.median().over(xo.window(group_by="species"))).filter(lambda t: t.x < t.med)
  ```
- **Honor "by-group" wording in the user's request** — if the user says "median by species" / "rank within region", the window MUST include `group_by="species"` / `group_by="region"`. Bare `xo.window()` (no `group_by`) is a global window and silently produces wrong-but-runnable results. Verify the SQL via `xorq_build debug=true` or `catalog_schema sql=true` if unsure.
- Reach for a build script (`xorq_build` + `catalog_add`) only after confirming the operation truly needs imports, multiple statements, or APIs not exposed via `xo`/`source`.

**Parameter name collisions:** `catalog_compose` does not currently expose `--rename-params` via the tool. Drop to bash (`xorq catalog compose ... --rename-params <entry>,<old>,<new> -a <alias>`) only when this is unavoidable.

## Building from a script

For a Python script that defines a xorq expression, call **`xorq_build`** with `script: <path>`.

- The default expression variable name is `expr`. Pass `expr_name` if the script uses a different variable.
- Build output goes to `builds/<hash>/`. The last line of stdout is the build path — capture it for the next step.
- Pass `debug: true` to emit SQL files for inspection.

## Running a built expression

Call **`xorq_run`** with `build_path` and an optional `format` / `limit` / `params` (e.g. `["threshold=0.5", "category=electronics"]`).

For *cataloged* entries, prefer **`catalog_run`** with the entry's name/alias.

## Running with caching

`xorq run-cached` is not wrapped by a tool. Use bash for it:

```bash
xorq run-cached <build_path> -f json --limit 20
```

- `--cache-type modification-time` (default): Re-runs when source file modification time changes
- `--cache-type snapshot`: Content-based cache, use with `--ttl` for periodic refresh

## Discovering available entries

Call **`catalog_list`** with `kind: true` to see entries with their kinds:

- **Source** (`source`) — bound, has data; use as source in composition
- **UnboundExpr** (`unbound_expr`) — partial transform, awaits input
- **Composed** (`composed`) — already composed; can be used as a source
- **ExprBuilder** (`expr_builder`) — ML pipeline or semantic model

Inspect a schema with **`catalog_schema`** (`name`, `json: true`).

## Tips

- See AGENTS.md Common Pitfalls for environment and API issues (VIRTUAL_ENV mismatch, `no_sync` only meaningful for `catalog_add`, compose requires `UnboundExpr` transforms, etc.)
- Start with `catalog_run` to test compositions before cataloging them with `catalog_compose`.
- Always use `dry_run: true` on `catalog_compose` when unsure about compatibility.
- The source entry must have `kind=Source` or `kind=Composed` (anything with bound data).
- Transform entries must have `kind=UnboundExpr`.
- The `code` parameter on `catalog_compose` is Ibis expression syntax applied to the `source` variable.
- Composed entries are tagged with `CatalogTag.SOURCE`, `CatalogTag.TRANSFORM`, and `CatalogTag.CODE` for provenance tracking.

## Arguments

If the user provides arguments: $ARGUMENTS — treat them as entry names to compose or run.
