# semantic-bts
A xorq demo project built around a **remote git catalog** of BTS On-Time flights
data and a [boring-semantic-layer](https://github.com/letsql/boring-semantic-layer)
model over it.


Unlike a typical project that authors its catalog in-tree, here the catalog
lives in a separate repo and is consumed as a git submodule:

```
semantic-bts/
├── src/semantic_bts/
│   ├── exprs/              # build scripts: flights, semantic-flights, aggregates
│   ├── build.py            # orchestrator: wipes + rebuilds the submodule catalog
│   └── _paths.py
├── xorq-catalog-bts/       # submodule -- the catalog (pristine remote starting point)
├── pi/                     # pi.dev extension + skills (vendored, agent integration)
└── AGENTS.md               # project rules for the pi agent
```

The catalog ships these entries:

- `flights` (source): BTS On-Time flights, fetched + cached as parquet
- `semantic-flights` (expr_builder): BSL semantic model (dims + measures)
- `flights-by-month-od-state` (expr): monthly metrics by origin/dest state
- `flights-by-quarter-carrier` (expr): quarterly metrics by airline
- `flights-by-dow-deststate` (expr): metrics by day-of-week + dest state

## Very Quickstart

Two nix only entry points: each self-clones the catalog into a scratch dir.

```bash
url=git+ssh://git@github.com/xorq-labs/semantic-bts   
# or https: github:xorq-labs/semantic-bts
nix run $url#tui   # browse the catalog in a terminal UI
nix run $url#pi    # drop into the pi.dev agent
```

Want a shell with the `semantic-bts`/`xorq` commands on `$PATH` instead? Clone
first (the catalog is a submodule); see below.

## Getting the source

```bash
git clone --recurse-submodules https://github.com/xorq-labs/semantic-bts
cd semantic-bts
cp .gitignore.template .gitignore   # local-only ignores (builds/, .venv, etc.)
```

If you already cloned without `--recurse-submodules`:

```bash
git submodule update --init --recursive
```

## Environment

Pick one. Both produce the same working environment (xorq + boring-semantic-layer + python 3.13).

### Nix (recommended)

```bash
nix develop
```

Builds a pinned dev shell from `flake.nix` (uv2nix-managed). All deps resolved
from `uv.lock`.

### uv

```bash
uv sync
source .venv/bin/activate
```

> **Note:** a uv-only env gives you the `semantic-bts`/`xorq` commands but
> **not** `pi`; the agent requires nix (`nix develop` or `nix run .#pi`).

## Using the catalog

The submodule ships a pre-built catalog (definitions only). The first `run`
fetches the underlying data and caches it locally, so you can use it
immediately without rebuilding the expressions:

```bash
xorq catalog -p xorq-catalog-bts list --kind
xorq catalog -p xorq-catalog-bts run flights -f json --limit 5
xorq catalog -p xorq-catalog-bts run flights-by-quarter-carrier -f json --limit 20
```

### Re-pointing the month range

The `flights` source exposes a deferred `year_months` parameter (a
comma-delimited string, default `2025_11,2025_12`). The neat part: that param
threads through **every** downstream expression, so you can re-point the whole
pipeline (source *or* any aggregate/semantic model) at a different month range
at execution time, no rebuild required:

```bash
# the source
xorq catalog -p xorq-catalog-bts run flights \
    --params year_months=2025_10,2025_11 -f json --limit 5

# ...and the same param flows into the aggregates built on top of it
xorq catalog -p xorq-catalog-bts run flights-by-quarter-carrier \
    --params year_months=2025_10,2025_11 -f json --limit 20
```

Or browse interactively with `xorq catalog -p xorq-catalog-bts tui`, a terminal UI for listing entries, inspecting schemas, and previewing rows.

## Rebuilding the catalog locally

Wipes the submodule catalog and rebuilds every entry from the source expressions
in `src/semantic_bts/exprs/`:

```bash
python -m semantic_bts.build
```

This produces content-addressed build artifacts under `builds/` (gitignored) and
re-registers them in `xorq-catalog-bts/` as the same aliases.

The orchestrator passes `--no-sync` to every `xorq catalog` call, so the
submodule's git remote is **never** pulled from or pushed to. The remote is
treated as a pristine starting point.

### CLI

The `semantic-bts` command is on your `$PATH` inside `nix develop`, or after
`uv sync` + activating the venv (`pip install -e .` works too):

```bash
semantic-bts list            # show catalog entries (alias, kind)
semantic-bts list-exprs      # show Python-importable expression names
semantic-bts show ALIAS      # show schema and metadata for an entry
semantic-bts run ALIAS       # execute an expression and print first rows
semantic-bts run ALIAS -n 20 # limit output to 20 rows
semantic-bts run flights --year-months 2025_10,2025_11  # re-point the month range
semantic-bts rebuild         # wipe + rebuild the submodule catalog
```

> These are thin shorthands over `xorq catalog -p xorq-catalog-bts ...`
> (`list-exprs` is package-specific). **`rebuild` is the only command with no
> `xorq` equivalent.** For everything else (`tui`, `add`, `remove`) use
> `xorq` directly.

### Python API

Expressions are available as lazy imports, with no catalog IO until you access one:

```python
from semantic_bts import flights, get_exprs, load

# lazy attribute access
flights.schema()
flights.limit(5).to_pandas()

# load by alias
load("flights-by-quarter-carrier").limit(10).to_pandas()

# re-point the deferred year_months param at execution time
load("flights").to_pandas(params={"year_months": "2025_10,2025_11"})

# get all expressions as a dict
exprs = get_exprs()  # {"flights": <expr>, "semantic-flights": <expr>, ...}
```

## Sharing the catalog with others (optional)

The default workflow is entirely local: rebuilds stay on your machine and
nothing is pushed to `xorq-labs/xorq-catalog-bts`. If you want to share your
catalog with others, fork the catalog repo on GitHub, point the submodule at
your fork with `git submodule set-url xorq-catalog-bts <your-fork>`, and push
from inside the submodule. This is not recommended for most use cases.

## Using pi.dev with the catalog

The `pi/` directory ships a [pi.dev](https://pi.dev/) extension + skills that
wire the agent into this project's catalog. The nix devShell pins it to
`xorq-catalog-bts/` (via `XORQ_CATALOG_PATH`) and forces `--no-sync` on every
mutating tool call, so the stock remote catalog is never accidentally pushed
to. **pi requires nix**; there is no non-nix bootstrap.

Launch it:

```bash
# From a clone :
nix develop && pi          # or, without a devShell: nix run .#pi

# No clone, self-clones the catalog into a scratch dir per invocation:
nix run github:xorq-labs/semantic-bts#pi                  # https
nix run "git+ssh://git@github.com/xorq-labs/semantic-bts#pi"   # ssh
```

> **If you change `pi/package-lock.json`:** set `npmDepsHash = lib.fakeHash`
> in `flake.nix`, run `nix build .#pi-bundle`; nix will print the correct
> SRI hash, then paste it back in.

The agent loads its project rules from the root `AGENTS.md`. Skills live in
`pi/skills/<name>/SKILL.md`; the xorq extension lives in
`pi/extensions/xorq.ts`.

## Appendix: trying it without cloning

If you just want to poke at the package (not the catalog, that needs the
submodule), you can run it straight from the git URL:

```bash
url=git+ssh://git@github.com/xorq-labs/semantic-bts   
# or https: github:xorq-labs/semantic-bts

# run the CLI via nix (no clone needed)
nix run $url -- list
nix run $url -- run flights-by-quarter-carrier -n 5


# drop into ipython with the package installed
uv tool run --isolated --python 3.13 --with $url ipython

# drop into a bash shell with the package on PATH (nix)
nix develop --refresh $url
```
