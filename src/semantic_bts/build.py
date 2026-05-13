"""Rebuild the xorq-catalog-bts submodule catalog from src exprs.

Usage:  uv run python -m semantic_bts.build

For each entry (in dependency order: flights -> semantic-flights ->
aggregates) this script:
  1. Removes the alias from the submodule catalog (if present), via
     `xorq catalog remove --no-sync`.
  2. Runs `xorq build <expr-file> -e <var>` to produce a content-addressed
     build directory under builds/.
  3. Adds the build back to the submodule via
     `xorq catalog add --no-sync -a <alias>`.

The `--no-sync` flag suppresses git pull/push on the submodule. The remote
remains the pristine starting point; rebuilds are local-only unless the
user explicitly publishes them.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from semantic_bts._paths import BUILDS_DIR, EXPRS_DIR, REPO_ROOT, SUBMODULE_PATH


@dataclass(frozen=True)
class Entry:
    alias: str
    script: Path
    expr_var: str


ENTRIES: tuple[Entry, ...] = (
    Entry("flights", EXPRS_DIR / "build_flights.py", "expr"),
    Entry("semantic-flights", EXPRS_DIR / "build_semantic_flights.py", "expr"),
    Entry(
        "flights-by-month-od-state",
        EXPRS_DIR / "build_aggregates.py",
        "expr_month_od",
    ),
    Entry(
        "flights-by-quarter-carrier",
        EXPRS_DIR / "build_aggregates.py",
        "expr_quarter_car",
    ),
    Entry(
        "flights-by-dow-deststate",
        EXPRS_DIR / "build_aggregates.py",
        "expr_dow_deststate",
    ),
)


def _xorq(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """Run the xorq CLI under the active uv environment."""
    cmd = ["uv", "run", "--active", "xorq", *args]
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def _xcat(*args: str, capture: bool = False) -> subprocess.CompletedProcess[str]:
    """xorq catalog operation targeting the submodule (never syncing)."""
    return _xorq("catalog", "-p", str(SUBMODULE_PATH), *args, capture=capture)


def existing_entries() -> list[str]:
    """Return every entry name (hash) currently in the submodule catalog.

    `xorq catalog list` emits one entry name per line; aliases are not
    included (`xorq catalog list-aliases` is the alias-only command).
    Removing by entry name also drops any aliases that pointed at it.
    """
    proc = _xcat("list", capture=True)
    out = proc.stdout or ""
    sys.stdout.write(out)
    names: list[str] = []
    for line in out.splitlines():
        parts = line.strip().split()
        if parts and not parts[0].startswith("#") and parts[0] != "No":
            names.append(parts[0])
    return names


def wipe_catalog() -> None:
    """Remove every entry (and its aliases) from the submodule catalog."""
    for name in existing_entries():
        _xcat("remove", "--no-sync", name)


def latest_build_dir(stdout: str) -> Path:
    """Locate the build directory `xorq build` just produced."""
    matches = re.findall(rf"{re.escape(str(BUILDS_DIR))}/[A-Za-z0-9_-]+", stdout)
    for hit in reversed(matches):
        path = Path(hit)
        if path.is_dir():
            return path
    if BUILDS_DIR.is_dir():
        dirs = [p for p in BUILDS_DIR.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        if dirs:
            return dirs[0]
    raise SystemExit(f"could not locate build output under {BUILDS_DIR}")


def build_and_add(entry: Entry) -> None:
    proc = _xorq(
        "build",
        str(entry.script),
        "-e",
        entry.expr_var,
        "--builds-dir",
        str(BUILDS_DIR),
        capture=True,
    )
    sys.stdout.write(proc.stdout or "")
    build_path = latest_build_dir(proc.stdout or "")
    _xcat("add", "--no-sync", str(build_path), "-a", entry.alias)


def main() -> int:
    if not (SUBMODULE_PATH / "catalog.yaml").exists():
        raise SystemExit(
            f"submodule catalog not found at {SUBMODULE_PATH}\n"
            f"run: git submodule update --init --recursive"
        )
    BUILDS_DIR.mkdir(exist_ok=True)
    os.chdir(REPO_ROOT)

    wipe_catalog()

    for entry in ENTRIES:
        build_and_add(entry)

    print("\n=== done ===", flush=True)
    _xcat("list", "--kind")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
