/**
 * xorq extension for pi.dev
 *
 * Registers tools and commands for interacting with xorq semantic catalogs.
 * The agent can discover, query, and execute catalog expressions directly
 * without writing boilerplate.
 *
 * Each tool wraps a single `xorq` CLI verb via `runXorq`. CLI verbs that may
 * emit useful stdout alongside a non-zero exit (e.g. `xorq catalog run`,
 * `xorq run`) opt into `allowNonZeroWithStdout` so the agent can still see
 * partial output but with the exit code surfaced in the text.
 *
 * Note on types: `pi.registerTool`'s `<TParams extends TSchema>` generic
 * combined with typebox-1.x schema types blows up TypeScript's instantiation
 * depth limit. We localise the type erasure in `defTool<P>` rather than
 * suppress checking for the whole file — every call site still gets a
 * statically typed `params` argument.
 */

import type {
  ExtensionAPI,
  ExtensionContext,
} from "@mariozechner/pi-coding-agent";
import { Type } from "typebox";
import { watch, existsSync, type FSWatcher } from "node:fs";
import { join } from "node:path";

// Timeouts grouped by intent so individual call sites stay self-documenting.
const TIMEOUT_FAST = 15_000; // info-style probes
const TIMEOUT_QUICK = 30_000; // list / schema / log
const TIMEOUT_MUTATE = 60_000; // add / remove / check / inline python
const TIMEOUT_RUN = 120_000; // catalog run / compose
const TIMEOUT_BUILD = 300_000; // xorq build / xorq run on a build dir
const TIMEOUT_SESSION_PROBE = 10_000; // session_start catalog detection
const WATCH_DEBOUNCE_MS = 750;

type ToolResult = {
  content: ReadonlyArray<{ type: "text"; text: string }>;
  details: object;
};

type ToolSpec<P> = {
  name: string;
  label: string;
  description: string;
  // Typebox schema. Kept opaque (`object`) here to avoid the
  // pi.registerTool × typebox generic depth issue; the per-tool `P`
  // parameter still constrains what `execute` receives.
  parameters: object;
  execute: (
    id: string,
    params: P,
    signal: AbortSignal | undefined,
  ) => Promise<ToolResult>;
};

// ---------------------------------------------------------------------
// Project-scoped catalog targeting.
//
// semantic-bts pins its catalog to the `xorq-catalog-bts/` submodule and
// keeps build artifacts under `./builds/`. The nix devShell (and the
// `nix run .#pi` wrapper) export XORQ_CATALOG_PATH and XORQ_BUILDS_DIR
// to absolute paths in the repo. We thread those into every `xorq catalog`
// and `xorq build` invocation so the agent never accidentally touches a
// user-level default catalog.
//
// When unset (e.g. someone runs the extension in an unrelated repo) we
// fall back to xorq's own defaults — same behaviour as before.
// ---------------------------------------------------------------------
const CATALOG_PATH = process.env.XORQ_CATALOG_PATH || "";
const BUILDS_DIR = process.env.XORQ_BUILDS_DIR || "";

function catalogArgs(...rest: string[]): string[] {
  return CATALOG_PATH
    ? ["catalog", "-p", CATALOG_PATH, ...rest]
    : ["catalog", ...rest];
}

function buildArgs(...rest: string[]): string[] {
  return BUILDS_DIR
    ? ["build", ...rest, "--builds-dir", BUILDS_DIR]
    : ["build", ...rest];
}

// ---------------------------------------------------------------------
// Easter eggs.
//
// Random emoticon/ASCII flair wraps tool output and the session-start
// greeting. Applied only to info-style tools — data-output tools whose
// stdout is parsed (catalog_run, catalog_schema, bsl_query, bsl_describe,
// xorq_build, xorq_run) opt out so decoration can't corrupt CSV/JSON or
// confuse the "last line is the build path" contract.
//
// Disable everything by setting PI_EASTER_EGGS=0.
// ---------------------------------------------------------------------
const EGG_GREETINGS = [
  "( •_•)>⌐■-■  semantic-bts online",
  "ʕ•ᴥ•ʔ  xorq says hi",
  "(づ｡◕‿‿◕｡)づ  ready to poke some flights",
  "~(˘▾˘~)  zero-flight stress",
  "(•_•) ( •_•)>⌐■-■ (⌐■_■)  catalog warmed up",
  "✧*｡٩(ˊᗜˋ*)و✧*｡  ready when you are",
  "ʕっ•ᴥ•ʔっ  the catalog and I are paws-itive about today",
] as const;

const EGG_BEFORE = [
  "( •_•)>⌐■-■   one sec...",
  "ʕっ•ᴥ•ʔっ   sniffing...",
  "~(˘▾˘~)   thinking...",
  "(っ◔◡◔)っ   hold the line",
  "*✲ﾟ*｡✧٩(･ิᴗ･ิ๑)۶   tally-ho",
  "(°ロ°)☝   one moment",
  "┬─┬ノ( º _ ºノ)   tidying tables",
] as const;

const EGG_AFTER = [
  "(⌐■_■)   ✓",
  "\\(^o^)/   done!",
  "(づ￣ ³￣)づ   xoxo",
  "ʕっ•ᴥ•ʔっ   served warm",
  "(´｡• ω •｡`)   ship it",
  "✧*｡٩(ˊᗜˋ*)و✧*｡   ✨",
  "(•_•) ( •_•)>⌐■-■ (⌐■_■)",
  "(งツ)ว   knock knock",
] as const;

const EGG_ART = [
  String.raw`
   ___  ___  ___  ___
  /   \/   \/   \/   \    ʕ•ᴥ•ʔ
  \___/\___/\___/\___/   semantic-bts
`,
  String.raw`
      __|__
  --o--(_)--o--    ( •_•)>⌐■-■
                   flight catalog ready
`,
  String.raw`
   .--.   .--.
  : (\). : (\).   (づ｡◕‿‿◕｡)づ
  '.__.' '.__.'    xorq + bsl
`,
  String.raw`
     /\_/\
    ( o.o )    \(^o^)/   ship it
     > ^ <
`,
] as const;

function eggsOn(): boolean {
  return process.env.PI_EASTER_EGGS !== "0";
}

function pickEgg<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function decorateText(text: string): string {
  if (!eggsOn()) return text;
  // Independent rolls so before/after pairing varies.
  const before = Math.random() < 0.55 ? pickEgg(EGG_BEFORE) + "\n\n" : "";
  const after = Math.random() < 0.55 ? "\n\n" + pickEgg(EGG_AFTER) : "";
  return `${before}${text}${after}`;
}

export default function (pi: ExtensionAPI) {
  const defTool = <P>(spec: ToolSpec<P>): void =>
    (pi.registerTool as (t: unknown) => void)(spec);

  // ---------------------------------------------------------------------
  // Helper: run `xorq <args>` and wrap stdout into a tool result.
  //
  // Most CLI verbs throw on non-zero exit. For `run`-style commands that
  // may emit useful stdout even when xorq exits non-zero, pass
  // `allowNonZeroWithStdout: true`; the helper then prefixes the text with
  // `[xorq exit N; stderr: ...]` so partial failures are visible to the
  // agent rather than silently swallowed.
  // ---------------------------------------------------------------------
  type RunOpts = {
    timeout?: number;
    signal?: AbortSignal;
    allowNonZeroWithStdout?: boolean;
    // Wrap output in easter-egg banners. Off by default — opt in only for
    // info-style tools whose output isn't position-parsed downstream.
    decorate?: boolean;
  };

  async function runXorq(args: string[], opts: RunOpts = {}): Promise<ToolResult> {
    const result = await pi.exec("xorq", args, {
      timeout: opts.timeout ?? TIMEOUT_QUICK,
      signal: opts.signal,
    });

    const maybeDecorate = (text: string): string =>
      opts.decorate ? decorateText(text) : text;

    if (opts.allowNonZeroWithStdout) {
      const out = result.stdout.trim();
      if (!out && result.code !== 0) {
        throw new Error(`xorq ${args.join(" ")} failed: ${result.stderr}`);
      }
      const text =
        result.code !== 0
          ? `[xorq exit ${result.code}; stderr: ${result.stderr.trim()}]\n${out}`
          : out;
      return { content: [{ type: "text", text: maybeDecorate(text) }], details: {} };
    }

    if (result.code !== 0) {
      throw new Error(
        `xorq ${args.join(" ")} failed: ${result.stderr || result.stdout}`,
      );
    }
    return {
      content: [{ type: "text", text: maybeDecorate(result.stdout || "OK") }],
      details: {},
    };
  }

  // -----------------------------------------------------------------------
  // Tool: catalog_list — list all available catalog entries
  // -----------------------------------------------------------------------
  defTool<{ kind?: boolean }>({
    name: "catalog_list",
    label: "List Catalog",
    description:
      "List all available entries in the xorq semantic catalog. " +
      "Use this to discover pre-computed data tables before loading raw files.",
    parameters: Type.Object({
      kind: Type.Optional(
        Type.Boolean({ description: "Show entry kinds (default: false)" }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs("list");
      if (params.kind) args.push("--kind");
      return runXorq(args, { signal, decorate: true });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_schema — show schema for a catalog entry
  // -----------------------------------------------------------------------
  defTool<{ name: string; json?: boolean }>({
    name: "catalog_schema",
    label: "Catalog Schema",
    description:
      "Show the column names and types for a catalog entry. " +
      "Use this to understand the structure of a pre-computed table.",
    parameters: Type.Object({
      name: Type.String({
        description: "The catalog entry name or alias to inspect",
      }),
      json: Type.Optional(
        Type.Boolean({ description: "Output as JSON (default: false)" }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs("schema", params.name);
      if (params.json) args.push("--json");
      return runXorq(args, { signal });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_run — execute a catalog entry and return results
  // -----------------------------------------------------------------------
  defTool<{ name: string; format?: string; limit?: number }>({
    name: "catalog_run",
    label: "Run Catalog Expression",
    description:
      "Execute a catalog expression and return the results. " +
      "Useful for quick data inspection without writing Python code.",
    parameters: Type.Object({
      name: Type.String({
        description: "The catalog entry name or alias to execute",
      }),
      format: Type.Optional(
        Type.String({
          description: "Output format: csv, json, or parquet (default: csv)",
          enum: ["csv", "json", "parquet"],
        }),
      ),
      limit: Type.Optional(
        Type.Number({ description: "Limit number of rows returned" }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs(
        "run",
        params.name,
        "-o",
        "/dev/stdout",
        "-f",
        params.format ?? "csv",
      );
      if (params.limit) args.push("--limit", String(params.limit));
      return runXorq(args, {
        signal,
        timeout: TIMEOUT_RUN,
        allowNonZeroWithStdout: true,
      });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_info — show catalog context and status
  // -----------------------------------------------------------------------
  defTool<Record<string, never>>({
    name: "catalog_info",
    label: "Catalog Info",
    description:
      "Show catalog location, remotes, and status. " +
      "Use this to check if a catalog is initialized and where it lives.",
    parameters: Type.Object({}),
    async execute(_id, _params, signal) {
      return runXorq(catalogArgs("info"), {
        signal,
        timeout: TIMEOUT_FAST,
        decorate: true,
      });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: penguins_fetch — fetch the penguins example dataset
  //
  // Inline-python escape hatch: lets users explore a known-good dataset
  // without checking data into the repo. Once they've done `init` for their
  // own data, that path supersedes this one.
  // -----------------------------------------------------------------------
  defTool<{ limit?: number }>({
    name: "penguins_fetch",
    label: "Fetch Penguins Dataset",
    description:
      "Fetch the xorq penguins example dataset and return its schema and preview.",
    parameters: Type.Object({
      limit: Type.Optional(
        Type.Number({
          description: "Number of preview rows (default: 5)",
        }),
      ),
    }),
    async execute(_id, params, signal) {
      const limit = Math.max(1, Math.floor(params.limit ?? 5));
      const script = `
import xorq.examples as ex
limit = ${limit}
t = ex.penguins.fetch()
print("Schema:")
print(t.schema())
print()
print(f"Preview ({limit} rows):")
print(t.head(limit).to_pandas().to_string())
print()
print(f"Total rows: {t.count().execute()}")
`.trim();

      const result = await pi.exec("python", ["-c", script], {
        timeout: TIMEOUT_MUTATE,
        signal,
      });

      if (result.code !== 0) {
        throw new Error(`penguins_fetch failed: ${result.stderr}`);
      }

      return {
        content: [{ type: "text", text: result.stdout }],
        details: {},
      };
    },
  });

  // -----------------------------------------------------------------------
  // Tool: bsl_describe — list dimensions and measures of a BSL ExprBuilder
  //
  // Replaces the `python -c "... .ls.builder; print(sorted(m.dimensions))"`
  // bash escape that agents otherwise reach for when discovering what a
  // semantic model can answer.
  // -----------------------------------------------------------------------
  defTool<{ name: string }>({
    name: "bsl_describe",
    label: "BSL Describe",
    description:
      "List dimensions and measures of a BSL semantic model entry. " +
      "Use this before `bsl_query` to discover available dims/measures. " +
      "The entry must be an ExprBuilder backed by boring-semantic-layer.",
    parameters: Type.Object({
      name: Type.String({
        description: "Catalog entry name or alias (BSL ExprBuilder).",
      }),
    }),
    async execute(_id, params, signal) {
      const script = `
import json, os
from xorq.catalog.catalog import Catalog
cat_path = os.environ.get("XORQ_CATALOG_PATH")
cat = Catalog.from_repo_path(cat_path) if cat_path else Catalog.from_default()
m = cat.load(${JSON.stringify(params.name)}).ls.builder
def _desc(obj):
    return getattr(obj, "description", None)
dims = m.get_dimensions()
meas = m.get_measures()
print(json.dumps({
    "name": getattr(m, "name", None),
    "dimensions": {k: _desc(v) for k, v in dims.items()},
    "measures":   {k: _desc(v) for k, v in meas.items()},
}, indent=2, default=str))
`.trim();
      const result = await pi.exec("python", ["-c", script], {
        timeout: TIMEOUT_MUTATE,
        signal,
      });
      if (result.code !== 0) {
        throw new Error(`bsl_describe failed: ${result.stderr}`);
      }
      return {
        content: [{ type: "text", text: result.stdout }],
        details: {},
      };
    },
  });

  // -----------------------------------------------------------------------
  // Tool: bsl_query — run a one-shot semantic query against a BSL model
  //
  // Short-circuits the "write build script -> xorq_build -> catalog_add ->
  // catalog_run" loop for analytical questions whose answer doesn't need
  // to be persisted in the catalog.
  // -----------------------------------------------------------------------
  defTool<{
    name: string;
    dimensions?: string[];
    measures?: string[];
    order_by?: string[];
    limit?: number;
    format?: string;
  }>({
    name: "bsl_query",
    label: "BSL Query",
    description:
      "Query a BSL semantic model entry by dimensions/measures and return results. " +
      "Use this for one-shot analytical questions — no build script needed. " +
      "Call `bsl_describe` first to discover dims/measures. " +
      "For a persistent derived entry, use the builder skill flow instead.",
    parameters: Type.Object({
      name: Type.String({
        description: "Catalog entry name or alias (BSL ExprBuilder).",
      }),
      dimensions: Type.Optional(
        Type.Array(Type.String(), {
          description: "Dimension names to group by.",
        }),
      ),
      measures: Type.Optional(
        Type.Array(Type.String(), {
          description: "Measure names to aggregate.",
        }),
      ),
      order_by: Type.Optional(
        Type.Array(Type.String(), {
          description: "Sort columns. Format: 'col' (asc) or 'col:desc'.",
        }),
      ),
      limit: Type.Optional(
        Type.Number({ description: "Limit number of rows returned." }),
      ),
      format: Type.Optional(
        Type.String({
          description: "Output format: csv or json (default: csv).",
          enum: ["csv", "json"],
        }),
      ),
    }),
    async execute(_id, params, signal) {
      const script = `
import json, os, sys
from xorq.catalog.catalog import Catalog
cat_path = os.environ.get("XORQ_CATALOG_PATH")
cat = Catalog.from_repo_path(cat_path) if cat_path else Catalog.from_default()
m = cat.load(${JSON.stringify(params.name)}).ls.builder
dims = ${JSON.stringify(params.dimensions ?? [])}
meas = ${JSON.stringify(params.measures ?? [])}
ob_raw = ${JSON.stringify(params.order_by ?? [])}
order_by = []
for s in ob_raw:
    if ":" in s:
        col, direction = s.split(":", 1)
    else:
        col, direction = s, "asc"
    order_by.append((col.strip(), direction.strip().lower()))
q = m.query(
    dimensions=tuple(dims),
    measures=tuple(meas),
    order_by=tuple(order_by) if order_by else None,
)
expr = q.to_untagged() if hasattr(q, "to_untagged") else q
df = expr.execute()
limit = ${params.limit ?? 0}
if limit:
    df = df.head(limit)
fmt = ${JSON.stringify(params.format ?? "csv")}
if fmt == "json":
    sys.stdout.write(df.to_json(orient="records"))
else:
    sys.stdout.write(df.to_csv(index=False))
`.trim();
      const result = await pi.exec("python", ["-c", script], {
        timeout: TIMEOUT_RUN,
        signal,
      });
      if (result.code !== 0) {
        throw new Error(`bsl_query failed: ${result.stderr}`);
      }
      return {
        content: [{ type: "text", text: result.stdout }],
        details: {},
      };
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_init — initialize a new catalog
  // -----------------------------------------------------------------------
  defTool<{ remote_url?: string }>({
    name: "catalog_init",
    label: "Initialize Catalog",
    description:
      "Initialize a new xorq catalog at the default location. " +
      "Use this when `catalog_info` reports the catalog is missing.",
    parameters: Type.Object({
      remote_url: Type.Optional(
        Type.String({ description: "Optional remote git URL to clone from" }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs("init");
      if (params.remote_url) args.push("--remote-url", params.remote_url);
      return runXorq(args, { signal, decorate: true });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_add — add a build directory to the catalog
  // -----------------------------------------------------------------------
  defTool<{ build_path: string; alias: string[]; no_sync?: boolean }>({
    name: "catalog_add",
    label: "Add to Catalog",
    description:
      "Add a build directory (output of `xorq_build`) to the catalog under one or more aliases.",
    parameters: Type.Object({
      build_path: Type.String({
        description: "Path to the build directory (e.g. builds/abc123).",
      }),
      alias: Type.Array(Type.String(), {
        description: "One or more aliases for the entry. At least one is required.",
        minItems: 1,
      }),
      no_sync: Type.Optional(
        Type.Boolean({
          description:
            "Defer pushing to the remote. Useful for batch adds (default: false).",
        }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs("add", params.build_path);
      for (const a of params.alias) args.push("--alias", a);
      // Force --no-sync when CATALOG_PATH is pinned (project catalog mode).
      // The pinned catalog is treated as a pristine remote; pushes would
      // overwrite the stock catalog. The user can opt out by clearing
      // XORQ_CATALOG_PATH and using `xorq` directly.
      if (params.no_sync || CATALOG_PATH) args.push("--no-sync");
      return runXorq(args, { signal, timeout: TIMEOUT_MUTATE, decorate: true });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_remove — remove entries from the catalog
  // -----------------------------------------------------------------------
  defTool<{ names: string[]; no_sync?: boolean }>({
    name: "catalog_remove",
    label: "Remove from Catalog",
    description:
      "Remove one or more entries from the catalog by name or alias. Destructive — confirm with the user first.",
    parameters: Type.Object({
      names: Type.Array(Type.String(), {
        description: "Entry names or aliases to remove.",
        minItems: 1,
      }),
      no_sync: Type.Optional(
        Type.Boolean({ description: "Defer pushing to the remote (default: false)." }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs("remove", ...params.names);
      // See catalog_add: force --no-sync in pinned-catalog mode.
      if (params.no_sync || CATALOG_PATH) args.push("--no-sync");
      return runXorq(args, { signal, timeout: TIMEOUT_MUTATE, decorate: true });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_compose — compose entries and add the result to the catalog
  // -----------------------------------------------------------------------
  defTool<{
    source: string;
    transforms?: string[];
    code?: string;
    alias?: string;
    dry_run?: boolean;
  }>({
    name: "catalog_compose",
    label: "Compose Catalog Entries",
    description:
      "Compose a source entry with transforms (or inline code) and add the result to the catalog. " +
      "Source must be kind=Source or kind=Composed; transforms must be kind=UnboundExpr. " +
      "Use `dry_run` to preview without persisting.",
    parameters: Type.Object({
      source: Type.String({ description: "Name or alias of the source entry." }),
      transforms: Type.Optional(
        Type.Array(Type.String(), {
          description: "UnboundExpr transform entries to apply in order.",
        }),
      ),
      code: Type.Optional(
        Type.String({
          description:
            "Single-expression inline ibis code applied to `source` (e.g. \"source.filter(source.amount > 100)\"). No imports/assignments.",
        }),
      ),
      alias: Type.Optional(
        Type.String({
          description: "Alias for the new composed entry. Required unless dry_run=true.",
        }),
      ),
      dry_run: Type.Optional(
        Type.Boolean({
          description: "Preview the composition without writing it (default: false).",
        }),
      ),
    }),
    async execute(_id, params, signal) {
      const args: string[] = catalogArgs("compose", params.source);
      for (const t of params.transforms ?? []) args.push(t);
      if (params.code) args.push("-c", params.code);
      if (params.alias) args.push("-a", params.alias);
      if (params.dry_run) args.push("--dry-run");
      return runXorq(args, { signal, timeout: TIMEOUT_RUN, decorate: true });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_log — show catalog operation history
  // -----------------------------------------------------------------------
  defTool<{ json?: boolean }>({
    name: "catalog_log",
    label: "Catalog Log",
    description: "Show the catalog's structured operation history.",
    parameters: Type.Object({
      json: Type.Optional(
        Type.Boolean({ description: "Output as JSON (default: false)." }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = catalogArgs("log");
      if (params.json) args.push("--json");
      return runXorq(args, { signal, decorate: !params.json });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: catalog_check — validate catalog consistency
  // -----------------------------------------------------------------------
  defTool<Record<string, never>>({
    name: "catalog_check",
    label: "Check Catalog",
    description:
      "Validate that catalog entries, aliases, metadata, and archives are consistent.",
    parameters: Type.Object({}),
    async execute(_id, _params, signal) {
      return runXorq(catalogArgs("check"), {
        signal,
        timeout: TIMEOUT_MUTATE,
        decorate: true,
      });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: xorq_build — build a Python expression script into a build directory
  // -----------------------------------------------------------------------
  defTool<{ script: string; expr_name?: string; debug?: boolean }>({
    name: "xorq_build",
    label: "Build Expression",
    description:
      "Compile a Python build script into a build directory (under ./builds/<hash>/). " +
      "The script must define an expression variable (default name `expr`). The last line of stdout is the build path — pass that to `catalog_add`.",
    parameters: Type.Object({
      script: Type.String({ description: "Path to the Python build script." }),
      expr_name: Type.Optional(
        Type.String({
          description: "Name of the expression variable to capture (default: `expr`).",
        }),
      ),
      debug: Type.Optional(
        Type.Boolean({ description: "Emit SQL files for inspection (default: false)." }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = buildArgs(params.script);
      if (params.expr_name) args.push("-e", params.expr_name);
      if (params.debug) args.push("--debug");
      return runXorq(args, { signal, timeout: TIMEOUT_BUILD });
    },
  });

  // -----------------------------------------------------------------------
  // Tool: xorq_run — run a built expression directory
  // -----------------------------------------------------------------------
  defTool<{
    build_path: string;
    format?: string;
    limit?: number;
    params?: string[];
  }>({
    name: "xorq_run",
    label: "Run Build",
    description:
      "Run a build directory produced by `xorq_build` and return the results. " +
      "For running cataloged entries by name/alias, use `catalog_run` instead.",
    parameters: Type.Object({
      build_path: Type.String({
        description: "Path to the build directory (e.g. builds/abc123).",
      }),
      format: Type.Optional(
        Type.String({
          description: "Output format: csv, json, or parquet (default: csv).",
          enum: ["csv", "json", "parquet"],
        }),
      ),
      limit: Type.Optional(
        Type.Number({ description: "Limit number of rows returned." }),
      ),
      params: Type.Optional(
        Type.Array(Type.String(), {
          description: "Repeatable key=value runtime parameters.",
        }),
      ),
    }),
    async execute(_id, params, signal) {
      const args = [
        "run",
        params.build_path,
        "-o",
        "/dev/stdout",
        "-f",
        params.format ?? "csv",
      ];
      if (params.limit) args.push("--limit", String(params.limit));
      for (const p of params.params ?? []) args.push("-p", p);
      return runXorq(args, {
        signal,
        timeout: TIMEOUT_BUILD,
        allowNonZeroWithStdout: true,
      });
    },
  });

  // -----------------------------------------------------------------------
  // Command: /catalog — quick catalog overview
  // -----------------------------------------------------------------------
  pi.registerCommand("catalog", {
    description: "Show xorq catalog overview",
    handler: async (_args, ctx) => {
      const result = await pi.exec("xorq", catalogArgs("info"), {
        timeout: TIMEOUT_FAST,
      });
      if (result.code !== 0) {
        ctx.ui.notify(
          "No xorq catalog found. Run `xorq catalog init` first.",
          "warning",
        );
        return;
      }

      pi.sendUserMessage(
        "Show the current catalog status and list all available entries. " +
          "Use the catalog_list tool.",
      );
    },
  });

  // -----------------------------------------------------------------------
  // Command: /wave — print random ASCII art (pure fun, opt-out via env)
  // -----------------------------------------------------------------------
  pi.registerCommand("wave", {
    description: "Wave hello with a random ASCII greeting",
    handler: async (_args, ctx) => {
      if (!eggsOn()) {
        ctx.ui.notify("easter eggs disabled (PI_EASTER_EGGS=0)", "info");
        return;
      }
      ctx.ui.notify(pickEgg(EGG_ART), "info");
    },
  });

  // -----------------------------------------------------------------------
  // Command: /xorq-reload — manually reload after catalog changes
  // -----------------------------------------------------------------------
  pi.registerCommand("xorq-reload", {
    description: "Reload pi resources after xorq catalog changes",
    handler: async (_args, ctx) => {
      await ctx.reload();
    },
  });

  // -----------------------------------------------------------------------
  // File watcher: detect catalog changes while pi is running.
  //
  // We can't call ctx.reload() directly from a non-command context — pi.dev
  // only exposes reload() on ExtensionCommandContext (see pi-coding-agent
  // examples/extensions/reload-runtime.ts). Instead we queue the
  // /xorq-reload slash command as a follow-up.
  // -----------------------------------------------------------------------
  const watchers: FSWatcher[] = [];
  let debounce: ReturnType<typeof setTimeout> | null = null;

  const scheduleReload = (reason: string, ctx: ExtensionContext) => {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(() => {
      debounce = null;
      ctx.ui.notify(
        `xorq catalog changed (${reason}) — reloading...`,
        "info",
      );
      pi.sendUserMessage("/xorq-reload", { deliverAs: "followUp" });
    }, WATCH_DEBOUNCE_MS);
  };

  const startWatching = (ctx: ExtensionContext) => {
    const targets = [join(ctx.cwd, "AGENTS.md"), join(ctx.cwd, "skills")];

    for (const path of targets) {
      if (!existsSync(path)) continue;
      try {
        const w = watch(
          path,
          { persistent: false, recursive: true },
          (_event, filename) => {
            scheduleReload(filename?.toString() ?? path, ctx);
          },
        );
        w.on("error", () => {
          /* swallow — e.g. file deleted mid-watch */
        });
        watchers.push(w);
      } catch {
        // non-fatal: path may not support watching on this platform
      }
    }
  };

  const stopWatching = () => {
    if (debounce) {
      clearTimeout(debounce);
      debounce = null;
    }
    for (const w of watchers.splice(0)) {
      try {
        w.close();
      } catch {
        /* ignore */
      }
    }
  };

  // -----------------------------------------------------------------------
  // Event: session start — check for catalog and start watchers
  // -----------------------------------------------------------------------
  pi.on("session_start", async (_event, ctx) => {
    const result = await pi.exec("xorq", catalogArgs("info"), {
      timeout: TIMEOUT_SESSION_PROBE,
    });

    if (result.code === 0) {
      const where = CATALOG_PATH
        ? ` (pinned: ${CATALOG_PATH}; mutations are --no-sync)`
        : "";
      const greeting = eggsOn() ? `  ${pickEgg(EGG_GREETINGS)}` : "";
      ctx.ui.setStatus(
        "xorq",
        `xorq catalog active${where} — use /catalog or catalog_list tool${greeting}`,
      );
      startWatching(ctx);
    }
  });

  // Clean up watchers on shutdown
  pi.on("session_shutdown", async () => {
    stopWatching();
  });
}
