"""Single source of truth for filesystem paths used by build scripts.

`_paths.py` is the only place that knows how the repo is laid out. Build
scripts and the orchestrator import constants from here so that moving
modules around requires editing exactly one file.
"""

from pathlib import Path


# This file is src/semantic_bts/_paths.py, so parents[2] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The xorq-catalog-bts submodule (pristine remote tracking the published catalog).
SUBMODULE_PATH = REPO_ROOT / "xorq-catalog-bts"

# Where `xorq build` writes its content-addressed build directories.
BUILDS_DIR = REPO_ROOT / "builds"

# Where build scripts live (one file per catalog entry, or per group).
EXPRS_DIR = Path(__file__).resolve().parent / "exprs"
