"""Public API for semantic_bts.

This package demonstrates xorq over the bundled `xorq-catalog-bts` submodule.
Loading a single entry is plain xorq — there is no wrapper for it:

    >>> from xorq.catalog.catalog import Catalog
    >>> from semantic_bts.api import SUBMODULE_PATH
    >>> cat = Catalog.from_repo_path(str(SUBMODULE_PATH))
    >>> cat.load("flights").limit(5).to_pandas()

The only project-specific entrypoints are:

  - `rebuild`    -- rebuild the catalog from `src/exprs/` (no xorq equivalent)
  - `get_exprs`  -- load every shipped entry at once, as ``{alias: expr}``

`ENTRIES` lists the build scripts and their aliases; `SUBMODULE_PATH` resolves
the pinned catalog regardless of cwd.
"""

from __future__ import annotations

from typing import Any

from xorq.catalog.catalog import Catalog

from semantic_bts._paths import SUBMODULE_PATH
from semantic_bts.build import ENTRIES

# Re-import rebuild under its public name
from semantic_bts.build import main as rebuild


__all__ = [
    "rebuild",
    "get_exprs",
    "ENTRIES",
    "SUBMODULE_PATH",
]


def get_exprs() -> dict[str, Any]:
    """Load all shipped catalog entries as ``{alias: expr}``."""
    cat = Catalog.from_repo_path(str(SUBMODULE_PATH))
    return {entry.alias: cat.load(entry.alias) for entry in ENTRIES}
