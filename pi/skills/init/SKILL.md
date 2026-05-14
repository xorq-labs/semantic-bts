---
description: Ingest CSV or Parquet files into a xorq catalog. Use when the user wants to onboard raw data files, create catalog entries from local files, or set up a new data source with an alias.
---

# Init — Ingest Data Files into a Catalog

Guide the user through turning raw CSV/Parquet files into cataloged, versioned xorq expressions.

## Workflow

### 1. Ensure a catalog exists

Check if a catalog is already initialized — call the **`catalog_info`** tool. If it errors with "Catalog not found", call **`catalog_init`** (pass `remote_url` if the user has a git remote in mind).

### 2. Write an ingestion script

Create a small Python script that reads the data file. The script must define an `expr` variable (the default name the `xorq_build` tool captures).

**For CSV files:**

```python
import xorq.api as xo

expr = xo.deferred_read_csv("/absolute/path/to/data.csv")
```

**For Parquet files:**

```python
import xorq.api as xo

expr = xo.deferred_read_parquet("/absolute/path/to/data.parquet")
```

**With transforms (optional):**

```python
import xorq.api as xo
from xorq.api import _

expr = xo.deferred_read_csv("/absolute/path/to/data.csv")
expr = expr.filter(_.amount > 0).select("id", "amount", "category")
```

Use absolute paths for data files.

### 3. Build the script

Call the **`xorq_build`** tool with `script: <path>`. The last line of its stdout is the build path (e.g. `builds/abc123…`).

### 4. Add to catalog with alias

Call the **`catalog_add`** tool with `build_path` (from step 3) and `alias` (one or more strings). The alias gives the entry a human-readable name.

### 5. Verify

Call **`catalog_list`** with `kind: true` to confirm the entry is registered, then **`catalog_schema`** with `json: true` to inspect its columns.

## Batch ingestion

When ingesting multiple files, run `xorq_build` + `catalog_add` once per script. Set `no_sync: true` on `catalog_add` if you want to defer pushing to the remote until the batch is complete.

## pyproject.toml setup

**IMPORTANT:** If `catalog_add` fails with `Multiple top-level packages discovered in a flat-layout`, add this to `pyproject.toml`:

```toml
[tool.setuptools]
py-modules = []
```

This prevents setuptools from auto-discovering data directories as Python packages.

## Tips

- See AGENTS.md Common Pitfalls for environment and API issues (VIRTUAL_ENV mismatch, flat-layout error, etc.)
- Pass `no_sync: true` to `catalog_add` if working without a remote.
- The `expr` variable name is the default for `xorq_build`. Pass `expr_name` if the script uses a different variable name.
- Pass `debug: true` to `xorq_build` to output SQL files for inspection.
- After adding, the entry kind should be `Source` (visible via `catalog_list` with `kind: true`).
- Use **absolute paths** for data files in scripts to avoid path resolution issues.
- `xorq_build`'s last stdout line is the build path — pass it to `catalog_add`.

## Arguments

If the user provides arguments: $ARGUMENTS — treat them as file path(s) to ingest.
