# semantic-bts — agent guide

This repo is a xorq demo built around the **`xorq-catalog-bts/` submodule**, a
remote git catalog of US BTS On-Time flights data, with a
[boring-semantic-layer](https://github.com/letsql/boring-semantic-layer)
semantic model on top.

The pi.dev extension and skills live under `pi/`. Read this file end-to-end
before answering — it pins down what you can touch and how.

## Project rules

1. **The catalog is `xorq-catalog-bts/` and only `xorq-catalog-bts/`.** The
   nix shell exports `XORQ_CATALOG_PATH` to its absolute path and the xorq
   extension threads `-p $XORQ_CATALOG_PATH` into every `xorq catalog …`
   call. Never edit a user-level default catalog.
2. **Never push to the catalog remote.** `xorq-catalog-bts` upstream is the
   pristine starting point. The extension forces `--no-sync` on every
   mutating tool call (`catalog_add`, `catalog_remove`) when
   `XORQ_CATALOG_PATH` is set. If you fall back to bash, you MUST pass
   `--no-sync` yourself.
3. **Builds go to `$XORQ_BUILDS_DIR`** (= `./builds/`), already wired into
   `xorq_build` — don't override it.
4. **Python and xorq come from the nix devShell venv.** Don't `uv run`,
   `uvx`, or `pip install` inside agent sessions; the binaries on PATH are
   already correct.

## Preferred tools (over raw bash)

| Tool | Use it for |
|------|-----------|
| `catalog_list` | What entries exist (`kind: true` to see kinds) |
| `catalog_schema` | Columns + types of an entry |
| `catalog_run` | Execute an entry by name/alias |
| `catalog_info` | Catalog location + status |
| `catalog_add` / `catalog_remove` | Mutate the pinned catalog (auto `--no-sync`) |
| `catalog_compose` | Compose source + transforms or inline `-c` code |
| `catalog_log` / `catalog_check` | History / consistency |
| `xorq_build` | Compile a script to `builds/<hash>/` |
| `xorq_run` | Run a built directory directly |
| `penguins_fetch` | Toy dataset for one-offs |

Bash-invoke `xorq` only for surface the tools don't expose
(`xorq catalog clone`, `xorq catalog tui`, `xorq catalog get`,
`xorq run-cached`). When you do, remember `-p $XORQ_CATALOG_PATH` and
`--no-sync`.

## Skills

`pi/skills/<name>/SKILL.md` — pi.dev preloads only descriptions. When a task
matches, **read the matching SKILL.md** before acting.

| Skill | Use when |
|-------|----------|
| `init` | Onboard raw CSV/Parquet files into the catalog |
| `builder` | Create ML pipelines (FittedPipeline), BSL semantic models, or custom TagHandler entries |
| `composer` | Compose / transform / run cataloged entries |
| `catalog-explore` | List entries, inspect schemas, understand pipeline structure |
| `ml-pipeline` | sklearn + xorq ML pipelines |

## Where to put new artifacts

- **New buildable expressions** belong in `src/semantic_bts/exprs/build_*.py`
  and should be appended to `ENTRIES` in `src/semantic_bts/build.py` so
  `python -m semantic_bts.build` reproduces them.
- One-off ad-hoc scripts are fine in `/tmp/` but prefer the `exprs/` route
  for anything worth keeping.

## Decision tree

1. User asks what data is available → `catalog_list` / `catalog-explore`
2. User wants to query an existing entry → `catalog_run`
3. **User asks an analytical question over flights/BSL data** (e.g. "delay
   % by X", "n_flights grouped by Y, ordered by Z") → `builder` skill, BSL
   section. Always inspect the `semantic-flights` model's `.dimensions` and
   `.measures` first; if the answer is a query over those names, it
   belongs in a builder-style derived entry (`model.query(...).to_untagged()`),
   NOT in `composer`. Composer's inline `-c` is for simple per-row
   filters/mutations on `Source` entries; using it to reimplement
   aggregates that already exist as BSL measures defeats the semantic
   layer.
4. User has raw files to onboard → `init` skill
5. User wants to combine two cataloged entries with simple per-row
   transforms → `composer` skill (try `catalog_compose -c` first; fall back
   to a build script for joins or anything multi-statement).
6. User wants an ML model → `ml-pipeline` or `builder` skill

## Common pitfalls

- **`xorq.examples` NOT `ibis.examples`.** Utf8View mismatches otherwise.
- **Window functions:** use explicit `win = xo.window(group_by=..., order_by=...)` then `col.<agg>().over(win)`. Inline kwargs on `.over(...)` can silently produce empty results for some aggregates (e.g. `median()`). Never use vanilla `ibis.window()` or `xo._.window(...)`.
- **Self-join from same source returns empty.** Use `mutate(... .over(xo.window(group_by=...)))` instead of joining a per-group aggregate back to the original table.
- **`catalog_compose -c` allowlist:** no `&`, `|`, `~`. Chain `.filter()` calls; for anything more involved, write a build script.
- **Build hashes are expression-graph based.** Editing comments / variable names doesn't change the hash; the expression has to change.
- **Utf8View vs Utf8.** `.cast("string")`. Cast strings AND narrow ints (`int8`/`int16` → `int64`) BEFORE caching/splitting in ML pipelines — the UDF signature locks at `fit()`.
- **Imports**
  - `from xorq.catalog.catalog import Catalog` — not `from xorq.catalog import Catalog`
  - `from xorq.expr.ml.pipeline_lib import Pipeline` — not `xo.Pipeline`
  - `import xorq.api as xo` for `xo.connect`, `deferred_read_*`
  - `import xorq.examples; xorq.examples.penguins.fetch()` — not submodule
- **`xorq.examples.<ds>.fetch()` returns a buildable `Table`.** Don't wrap in `xo.memtable(...)` or pass to `con.create_table(...)`.
- **`ibis.duckdb.connect()` produces vanilla ibis Tables that fail `xorq build`.** Use `xo.deferred_read_*` or `xorq.examples`.
- **BSL recovery:** `from_tagged(cat.load(alias))` fails — `cat.load()` wraps in HashingTag. Walk `loaded_expr.ls.get_tags()`, find the tag where `t.tag == "bsl"`, then `from_tagged(tag.to_expr())`.
- **BSL queries:** `model.query(...)` returns `SemanticAggregate` which is NOT buildable. Use `model.to_tagged()` for `xorq build`. To query specific dims/measures AND build, call `model.query(...).to_tagged()` if available, otherwise `model.to_tagged()` and post-filter.
- **Custom TagHandler:** must be registered in EVERY process, including inside build scripts (subprocesses).
- **`--no-sync`:** add/remove accept it; compose does not.
- **Flat-layout error on `catalog_add`:** add `[tool.setuptools] py-modules = []` to `pyproject.toml`.
