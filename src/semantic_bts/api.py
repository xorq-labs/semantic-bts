"""Public API for semantic_bts.

This package wraps the bundled `xorq-catalog-bts` submodule. The functions
below are the intended entrypoints; everything else (`build`, `exprs/`,
`_paths`) is an implementation detail.

Example:
    >>> from semantic_bts.api import catalog, load
    >>> cat = catalog()
    >>> flights = load("flights")
    >>> flights.limit(5).to_pandas()

Expressions are also available as lazy module-level attributes::

    >>> from semantic_bts.api import flights
    >>> flights.schema()
"""

from __future__ import annotations

from typing import Any

from xorq.catalog.catalog import Catalog

from semantic_bts._paths import SUBMODULE_PATH
from semantic_bts.build import ENTRIES

# Re-import rebuild under its public name
from semantic_bts.build import main as rebuild


# Map Python-safe names (underscores) to catalog aliases (hyphens)
_ALIAS_MAP: dict[str, str] = {
    e.alias.replace("-", "_"): e.alias for e in ENTRIES
}

__all__ = [
    "catalog",
    "load",
    "rebuild",
    "get_exprs",
    "ENTRIES",
    "SUBMODULE_PATH",
    *_ALIAS_MAP,  # expression aliases (lazy-loaded via __getattr__)
]


def catalog() -> Catalog:
    """Open the bundled BTS catalog rooted at the submodule.

    The catalog is treated as read-only — `rebuild()` is the only way to
    mutate it from this package, and it passes `--no-sync` to xorq so the
    submodule's git remote is never touched.
    """
    return Catalog.from_repo_path(str(SUBMODULE_PATH))


def load(alias: str):
    """Load a single catalog entry by alias (`flights`, `semantic-flights`, ...)."""
    return catalog().load(alias)


def get_exprs() -> dict[str, Any]:
    """Load all catalog entries as ``{alias: expr}`` dict."""
    return {entry.alias: load(entry.alias) for entry in ENTRIES}


def __getattr__(name: str):
    if name in _ALIAS_MAP:
        return load(_ALIAS_MAP[name])
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
