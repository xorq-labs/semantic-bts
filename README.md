# semantic-bts
A xorq demo project built around a **remote git catalog** of BTS On-Time flights
data and a [boring-semantic-layer](https://github.com/letsql/boring-semantic-layer)
model over it.

![Not this BTS](assets/image.png)



Unlike a typical project that authors its catalog in-tree, here the catalog
lives in a separate repo and is consumed as a git submodule:

```
semantic-bts/
├── src/semantic_bts/
│   ├── exprs/              # build scripts: flights, semantic-flights, aggregates
│   ├── build.py            # orchestrator: wipes + rebuilds the submodule catalog
│   └── _paths.py
├── xorq-catalog-bts/       # submodule -- the catalog (pristine remote starting point)
└── porq/                   # submodule -- pi.dev + xorq integration (optional)
```

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

### Nix

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

## Using the catalog

The submodule ships a pre-built catalog — you can use it immediately without
rebuilding:

```bash
xorq catalog -p xorq-catalog-bts list --kind
xorq catalog -p xorq-catalog-bts run flights -f json --limit 5
xorq catalog -p xorq-catalog-bts run flights-by-quarter-carrier -f json --limit 20
```

Or browse interactively with `xorq catalog -p xorq-catalog-bts tui` — a terminal UI for listing entries, inspecting schemas, and previewing rows.

Entries:

| alias                          | kind          | what                                            |
|--------------------------------|---------------|-------------------------------------------------|
| `flights`                      | source        | BTS On-Time flights, fetched + cached as parquet|
| `semantic-flights`             | expr_builder  | BSL semantic model (dims + measures)            |
| `flights-by-month-od-state`    | expr          | monthly metrics by (origin_state, dest_state)   |
| `flights-by-quarter-carrier`   | expr          | quarterly metrics by reporting_airline          |
| `flights-by-dow-deststate`     | expr          | (day_of_week, dest_state_name) metrics          |

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

### Python API

Expressions are available as lazy imports — no catalog IO until you access one:

```python
from semantic_bts import flights, get_exprs, load

# lazy attribute access
flights.schema()
flights.limit(5).to_pandas()

# load by alias
load("flights-by-quarter-carrier").limit(10).to_pandas()

# get all expressions as a dict
exprs = get_exprs()  # {"flights": <expr>, "semantic-flights": <expr>, ...}
```

### CLI

If you `uv sync` / `pip install -e .` this repo, the `semantic-bts` command
lands on your `$PATH`:

```bash
semantic-bts list            # show catalog entries (alias, kind)
semantic-bts list-exprs      # show Python-importable expression names
semantic-bts show ALIAS      # show schema and metadata for an entry
semantic-bts run ALIAS       # execute an expression and print first rows
semantic-bts run ALIAS -n 20 # limit output to 20 rows
semantic-bts rebuild         # wipe + rebuild the submodule catalog
```

For richer catalog ops — `tui`, `add`, `remove`, etc. — use the underlying
`xorq` CLI directly.

## Sharing the catalog with others (optional)

The default workflow is entirely local — rebuilds stay on your machine and
nothing is pushed to `xorq-labs/xorq-catalog-bts`. If you want to share your
catalog with others, fork the catalog repo on GitHub, point the submodule at
your fork with `git submodule set-url xorq-catalog-bts <your-fork>`, and push
from inside the submodule. This is not recommended for most use cases.

## Using pi.dev with the catalog

The `porq` submodule wires xorq's catalog into the [pi.dev](https://pi.dev/)
coding agent — it gives the agent tools to list, inspect, and run catalog
entries. If you want an agent to help you explore or extend this catalog:

```bash
cd porq
nix develop      # or: ./setup.sh && source .venv/bin/activate && export PATH="$PWD/node_modules/.bin:$PATH"
pi               # launch the agent
# ... work with the agent ...
cd ..            # hop back up
```

See `porq/README.md` for details. Skip this section entirely if you just want
to use the catalog from the CLI or Python.

## Appendix: trying it without cloning

If you just want to poke at the package (not the catalog — that needs the
submodule), you can run it straight from the git URL:

```bash
url=git+ssh://git@github.com/xorq-labs/semantic-bts

# run the package's __main__
uv tool run --isolated --python 3.13 --with $url -- python -m semantic_bts

# run the project script entrypoint via nix
nix develop --refresh $url --command semantic-bts

# drop into ipython with the package installed
uv tool run --isolated --python 3.13 --with $url ipython

# drop into a bash shell with the package on PATH (nix)
nix develop --refresh $url
```

> Append `@<branch>` (uv) or `?ref=<branch>` (nix) to the url to target a
> branch. Use `ssh://git@` instead of `https://` for private repos.
