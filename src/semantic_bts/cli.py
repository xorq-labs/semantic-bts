"""Thin CLI over the bundled BTS catalog.

Two commands:
  semantic-bts list      -- show catalog entries (alias, kind)
  semantic-bts rebuild   -- wipe and rebuild the submodule catalog

For richer catalog ops use `xorq catalog -p xorq-catalog-bts ...` directly.
"""

from __future__ import annotations

import click

from semantic_bts.api import ENTRIES, catalog
from semantic_bts.api import rebuild as _rebuild


@click.group()
def cli() -> None:
    pass


@cli.command(name="list")
def list_entries() -> None:
    """Print the aliases this package ships with."""
    cat = catalog()
    for entry in ENTRIES:
        try:
            handle = cat.load(entry.alias)
            kind = type(handle).__name__
        except Exception as exc:  # noqa: BLE001
            kind = f"<unloadable: {exc.__class__.__name__}>"
        click.echo(f"{entry.alias:30s} {kind}")


@cli.command()
def rebuild() -> None:
    """Wipe the submodule catalog and rebuild every entry from src/exprs/."""
    raise SystemExit(_rebuild())
