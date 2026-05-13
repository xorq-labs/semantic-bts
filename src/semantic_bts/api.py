"""Public API for semantic_bts.

This package wraps the bundled `xorq-catalog-bts` submodule. The functions
below are the intended entrypoints; everything else (`build`, `exprs/`,
`_paths`) is an implementation detail.

Example:
    >>> from semantic_bts.api import catalog, load
    >>> cat = catalog()
    >>> flights = load("flights")
    >>> flights.limit(5).to_pandas()
"""

from __future__ import annotations

from xorq.catalog.catalog import Catalog

from semantic_bts._paths import SUBMODULE_PATH
from semantic_bts.build import ENTRIES
from semantic_bts.build import main as rebuild


__all__ = [
    "catalog",
    "load",
    "rebuild",
    "ENTRIES",
    "SUBMODULE_PATH",
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
