---
description: Create ExprBuilder catalog entries — ML pipelines (FittedPipeline), semantic models (BSL), or custom TagHandlers. Use when the user wants to fit a model, create a semantic layer entry, or register a custom builder for round-trip recovery.
---

# Builder — Create ExprBuilder Entries

Guide the user through creating catalog entries with recoverable domain objects via the TagHandler registry. This covers ML pipelines, semantic models (BSL), and custom builders.

## ML Pipelines (FittedPipeline)

### Prerequisites

**sklearn must be installed.** If not already in dependencies, add it:

```bash
uv add scikit-learn
# or add "scikit-learn" to pyproject.toml dependencies
```

### Workflow

#### 1. Write a training script

Create a Python script that fits a pipeline and produces a tagged expression:

```python
import xorq.api as xo
from xorq.expr.ml.pipeline_lib import Pipeline
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

# Load training data — use ABSOLUTE paths
train = xo.deferred_read_csv("/absolute/path/to/train.csv")

# Create and fit pipeline
sk_pipe = make_pipeline(StandardScaler(), LogisticRegression())
pipeline = Pipeline.from_instance(sk_pipe)
fitted = pipeline.fit(train, features=["feature1", "feature2"], target="label")

# Produce tagged prediction expression
expr = fitted.predict(train)
```

**IMPORTANT — correct imports (see AGENTS.md Common Pitfalls for full list):**
- `from xorq.expr.ml.pipeline_lib import Pipeline` — this is the correct import for build scripts
- Do NOT use `xo.Pipeline` in build scripts — see AGENTS.md "ML Pipeline import" pitfall
- Do NOT use `deferred_fit_predict` — see AGENTS.md "ML Pipeline API" pitfall

**Key points:**
- `Pipeline.fit()` is **deferred** — it builds an expression graph, it does not execute sklearn immediately
- `.predict()` tags the expression with `FittedPipelineTagKey.PREDICT`
- Other response methods: `.transform()`, `.predict_proba()`, `.decision_function()`, `.feature_importances()`
- The `features` parameter takes a list of column names; `target` is the label column
- Features must be **numeric columns** — filter out non-numeric columns before fitting

#### 2. Build the script

Call the **`xorq_build`** tool with `script: <path>`. The last line of stdout is the build path.

#### 3. Add to catalog

Call **`catalog_add`** with `build_path` (from step 2) and `alias` (e.g. `["my-model"]`).

#### 4. Verify

Call **`catalog_list`** with `kind: true` — the entry kind should be `expr_builder`. Inspect its schema with **`catalog_schema`** (`json: true`).

#### 5. Round-trip test (optional)

Write a script that loads from catalog, recovers the pipeline, and predicts on new data:

```python
import xorq.api as xo
from xorq.catalog.catalog import Catalog

cat = Catalog.from_default()
ml_expr = cat.load("<model-name>")  # NOT catalog["name"] — use .load()

# Recover the FittedPipeline domain object
fitted_pipeline = ml_expr.ls.builder

# Predict on new data
new_data = xo.deferred_read_csv("/absolute/path/to/test.csv")
predictions = fitted_pipeline.predict(new_data)
expr = predictions  # this is what xorq build captures
```

**IMPORTANT API notes** (see AGENTS.md Common Pitfalls for details):
- Use `Catalog.from_default()` — `xo.catalog()` is a module, not callable
- Use `cat.load("alias")` — NOT `cat["alias"]`
- Use `xo.deferred_read_csv()` / `xo.deferred_read_parquet()` in build scripts

## BSL (Boring Semantic Layer)

BSL entries wrap expressions with semantic model metadata (dimensions, measures, descriptions).

### Creating a BSL expression

**API (verified):** `SemanticModel(table=expr, dimensions={name: Dimension(expr=lambda t: t.col)}, measures={name: Measure(expr=lambda t: t.col.sum())})`

```python
import xorq.api as xo
from boring_semantic_layer import SemanticModel, Dimension, Measure

source = xo.deferred_read_csv("/absolute/path/to/data.csv")

# Dimensions and measures are DICTS (not lists), values use lambda expr
model = SemanticModel(
    table=source,
    name="my_model",
    dimensions={
        "category": Dimension(expr=lambda t: t.category),
        "region": Dimension(expr=lambda t: t.region),
    },
    measures={
        "total_amount": Measure(expr=lambda t: t.amount.sum()),
        "avg_amount": Measure(expr=lambda t: t.amount.mean()),
    },
)

# to_tagged() produces the buildable expression for xorq build
expr = model.to_tagged()

# Or query first then use to_tagged on the model:
# queried = model.query(dimensions=["category"], measures=["total_amount"])
```

### Recovery from catalog

Two ways to get the `SemanticModel` back out of a cataloged BSL entry:

**(a) Fast path — `.ls.builder` (works inside a build script):**

```python
from xorq.catalog.catalog import Catalog
cat = Catalog.from_repo_path("xorq-catalog-bts")   # or Catalog.from_default()
model = cat.load("semantic-flights").ls.builder    # recovered SemanticModel
```

This works whenever the BSL TagHandler is registered in the current
process — true by default inside `xorq build` scripts in this repo.

**(b) Tag-walking path — when `.ls.builder` returns the wrong shape:**

```python
from boring_semantic_layer import from_tagged
from xorq.catalog.catalog import Catalog

cat = Catalog.from_default()
loaded_expr = cat.load("my_bsl_entry")

tags = loaded_expr.ls.get_tags()
bsl_tag = [t for t in tags if hasattr(t, "tag") and t.tag == "bsl"][0]
model = from_tagged(bsl_tag.to_expr())
```

### Answering analytical questions against a BSL model

**Decide first: one-shot or persisted?**

- **One-shot** ("what's X by Y?") — use **`bsl_query`** directly. No build
  script, no catalog entry. Fastest path.
- **Persisted / reproducible** (the result should live in the catalog and
  rebuild from `python -m semantic_bts.build`) — follow the build script
  flow below.

### One-shot path

1. `catalog_list kind:true` → find the BSL `ExprBuilder` entry.
2. `bsl_describe name:<entry>` → discover dims/measures. Do NOT fall back
   to `python -c "... .ls.builder ..."` — the tool is authoritative.
3. `bsl_query name:<entry> dimensions:[...] measures:[...] order_by:[...]
   limit:<n>` → results as CSV.

If the question genuinely needs a dim or measure that doesn't exist, say
so and ask whether to extend the BSL model — don't invent names or reach
for raw `flights`.

### Persisted path — deriving a new catalog entry from a recovered BSL model

The pattern is:

1. **Discover the BSL entry** with `catalog_list` (kind: true) — look for
   `ExprBuilder` entries.
2. **Introspect dims/measures** with **`bsl_describe`** (tool). Match the
   user's question against those names — don't invent new ones.

3. **Write a tiny build script under `src/semantic_bts/exprs/build_<topic>.py`**
   that loads the model, queries it, and untags the result:

   ```python
   from xorq.catalog.catalog import Catalog
   from semantic_bts._paths import SUBMODULE_PATH

   model = Catalog.from_repo_path(str(SUBMODULE_PATH)).load(
       "semantic-flights"
   ).ls.builder

   expr = model.query(
       dimensions=[...],    # from step 2
       measures=[...],      # from step 2
       order_by=[(..., "asc")],
   ).to_untagged()
   ```

   - **`SemanticAggregate.to_untagged()` IS buildable** by `xorq build`
     (verified — see `src/semantic_bts/exprs/build_aggregates.py`). Use it
     for ad-hoc derived entries — the result is a plain aggregate, NOT
     another ExprBuilder.
   - Use `model.to_tagged()` (no query) ONLY when you want the entry to
     remain a round-trippable BSL model (an ExprBuilder kind).
   - The expression variable name must be exposed as a top-level binding
     `expr` (or pass `expr_name` to `xorq_build`).

4. **Build + add** via the tools:
   - `xorq_build` with `script: src/semantic_bts/exprs/build_<topic>.py`
   - `catalog_add` with the printed build path and a descriptive alias
     (e.g. `flights-delay-pct-by-time-block`)
   - The extension auto-injects `-p $XORQ_CATALOG_PATH` and `--no-sync`
     — don't push to the catalog remote.

5. **Verify** with `catalog_list kind:true` (new entry should appear as
   `Composed`), then `catalog_run name:<alias> format:csv limit:24`.

6. **Make it reproducible** — append a new `Entry(...)` to `ENTRIES` in
   `src/semantic_bts/build.py` pointing at the new script so
   `python -m semantic_bts.build` rebuilds it.

### Notes

- The cataloged expression is tagged with `"bsl"` containing the
  SemanticModel metadata (visible via `catalog_schema`).
- `entry.expr.ls.builder` returns the recovered domain object (the
  `SemanticModel` itself) when the TagHandler is registered.
- An entry built from `model.to_tagged()` has kind `ExprBuilder`; one
  built from `model.query(...).to_untagged()` has kind `Composed`.

## Custom TagHandlers

### Registration via Python

**CRITICAL:** The TagHandler must be registered in EVERY Python process that needs it (see AGENTS.md "Custom TagHandler per-process" pitfall). Since `xorq build` spawns a subprocess, you must register the handler **inside the build script itself** (not in a separate setup step).

**`.tag()` API:** `expr.tag("tag_name", key=value, key2=value2)` — string tag name + keyword args. NOT a dict.

```python
import xorq.api as xo
from xorq.expr.builders import register_tag_handler, TagHandler

# Register — MUST happen before .ls.builder is called
register_tag_handler(TagHandler(
    tag_names=("my_custom_tag",),
    extract_metadata=lambda tag_node: {"type": "my_custom_tag", "column": tag_node.metadata.get("column", "")},
    from_tag_node=lambda tag_node: dict(tag_node.metadata),
))

# Tag an expression — use string tag name + kwargs (NOT a dict!)
source = xo.deferred_read_csv("/absolute/path/to/data.csv")
expr = source.tag("my_custom_tag", column="age", threshold=0.5)
# tag_node.metadata will be {"tag": "my_custom_tag", "column": "age", "threshold": 0.5}
```

### Complete round-trip example (build + recover)

**Script 1: Create and catalog the tagged expression**
```python
import xorq.api as xo
from xorq.expr.builders import register_tag_handler, TagHandler

register_tag_handler(TagHandler(
    tag_names=("my_custom_tag",),
    extract_metadata=lambda tn: {"type": "my_custom_tag", "column": tn.metadata.get("column", "")},
    from_tag_node=lambda tn: dict(tn.metadata),
))

source = xo.deferred_read_csv("/path/to/data.csv")
expr = source.tag("my_custom_tag", column="age", transform="filter_positive")
```

**Script 2: Recover from catalog and create new expression**
```python
import xorq.api as xo
from xorq.expr.builders import register_tag_handler, TagHandler
from xorq.catalog.catalog import Catalog

# MUST re-register handler in this process too
register_tag_handler(TagHandler(
    tag_names=("my_custom_tag",),
    extract_metadata=lambda tn: {"type": "my_custom_tag", "column": tn.metadata.get("column", "")},
    from_tag_node=lambda tn: dict(tn.metadata),
))

cat = Catalog.from_default()
loaded_expr = cat.load("my_tagged_entry")
builder = loaded_expr.ls.builder  # returns dict from from_tag_node

# Use recovered metadata to create a new expression
new_data = xo.deferred_read_csv("/path/to/new_data.csv")
expr = new_data.tag("my_custom_tag", **{k: v for k, v in builder.items() if k != "tag"}, derived=True)
```

### Registration via entry point (persistent across processes)

In `pyproject.toml`:

```toml
[project.entry-points."xorq.from_tag_node"]
my_handler = "my_package.handlers:my_tag_handler"
```

This avoids needing to re-register in every script.

### How it works

1. Tag an expression: `expr.tag("my_custom_tag", key=value, ...)` — string name + kwargs (verified signature: `Table.tag(self, tag, **kwargs)`)
2. Build and add to catalog — entry kind becomes `ExprBuilder`
3. On load: `entry.expr.ls.builder` dispatches to registered handler's `from_tag_node()`
4. `extract_metadata()` stores handler metadata in catalog sidecar YAML (`ExprMetadata.builders`)

### Requirements

- At least one of `extract_metadata` or `from_tag_node` must be provided
- `tag_names` is a tuple of string tag names the handler responds to
- Builtin tag names (`bsl`, ML pipeline tags) cannot be overridden without `override=True`
- Tag metadata values (kwargs to `.tag()`) must be hashable — see AGENTS.md "Custom TagHandler hashability" pitfall

## Tips

- **Build hash collision**: A BSL or ML expression built from the same source data may produce the same build hash as the source's original build. This overwrites the `builds/<hash>/` directory. Always `catalog_add` the builder entry BEFORE rebuilding the source, or fall back to bash with `xorq build --builds-dir <other>` when isolation is needed.
- ML pipeline `fit()` is deferred — the actual sklearn fitting happens at `xorq_run` time, not at script execution
- The training source is structurally embedded in the expression graph — `FittedPipeline.from_tag_node()` walks the graph to find it
- `ExprMetadata.builders` stores extracted metadata so you can inspect pipeline steps without fetching the full archive
- Use `xorq_run` with `format: "json"` and `limit: 10` to preview predictions before cataloging

## Arguments

If the user provides arguments: $ARGUMENTS — treat them as a description of the builder type or model to create.
