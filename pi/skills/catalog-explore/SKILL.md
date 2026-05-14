---
description: Explore a xorq catalog — list entries, inspect schemas, and understand available data expressions. Use when the user asks about what's in a catalog, what expressions are available, or wants to understand a pipeline's inputs and outputs.
---

# Catalog Explorer

Use the registered tools to help the user explore their catalog.

## Workflow

### 1. Discover entries

Call **`catalog_list`** with `kind: true` to list entries with their kinds.

The catalog tools are pinned to `$XORQ_CATALOG_PATH` (set by the nix shell to the project's `xorq-catalog-bts/` submodule). The user is asking about that catalog — do not look elsewhere. Only fall back to bash with `-p <other-path>` if the user explicitly asks about a different catalog.

### 2. Inspect schemas

For entries of interest, call **`catalog_schema`** (`name`, `json: true`). This shows `schema_in` (input parameters) and `schema_out` (output columns) with types.

### 3. Catalog context

Call **`catalog_info`** to see the catalog's location, remotes, and size.

### 4. History

Call **`catalog_log`** with `json: true` for structured operation history.

### 5. Consistency check

Call **`catalog_check`** to validate that entries, aliases, metadata, and archives are consistent.

## Loading Data

```python
from xorq.catalog.catalog import Catalog

cat = Catalog.from_default()
df = cat.load("alias-name").execute()
```

## Semantic Model Queries

Some entries are backed by **boring-semantic-layer** semantic models with typed dimensions and measures:

```python
model = cat.load("semantic-entry")
builder = model.ls.builder

# Query specific dimensions and measures
result = builder.query(
    dimensions=("card_scheme", "year"),
    measures=("fraud_volume", "volume")
).execute()
```

## Presenting results

- Summarize entries in a table: name, kind (Source, UnboundExpr, Composed, ExprBuilder), and key columns.
- When showing schemas, highlight the input parameters (`schema_in`) vs output columns (`schema_out`).
- If an entry is `UnboundExpr` (partial), explain that it requires input data to run — it's a reusable transform.
- If an entry is `ExprBuilder`, note that it contains a recoverable domain object (e.g., ML pipeline, semantic model).
- If an entry is `Composed`, note that it was assembled from other catalog entries.

## Decision Tree

1. **Question about data?** Call `catalog_list` (`kind: true`) for relevant entries
2. **Found an entry?** Run it via `catalog_run`, or load it in Python with `Catalog.from_default().load(...)`
3. **Need custom aggregation?** Call `catalog_compose` (or `catalog_run` with `code`) to transform the closest entry
4. **No relevant entry?** Load raw data, but consider building a new expression and adding it via `xorq_build` + `catalog_add` for reuse
5. **Complex domain logic (fees, rates)?** Almost certainly in the catalog already

## Arguments

If the user provides arguments: $ARGUMENTS — treat them as a catalog name or entry name to focus on.
