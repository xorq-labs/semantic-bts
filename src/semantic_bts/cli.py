"""Thin CLI over the bundled BTS catalog.

Commands:
  semantic-bts list        -- show catalog entries (alias, kind)
  semantic-bts list-exprs  -- show Python-importable expression names
  semantic-bts run ALIAS   -- execute an expression and print result
  semantic-bts show ALIAS  -- show schema and metadata for an entry
  semantic-bts rebuild     -- wipe and rebuild the submodule catalog

For richer catalog ops use `xorq catalog -p xorq-catalog-bts ...` directly.
"""

from __future__ import annotations

import click

from semantic_bts.api import _ALIAS_MAP, ENTRIES, catalog, load
from semantic_bts.api import rebuild as _rebuild


def _complete_alias(_ctx, _param, incomplete: str) -> list[str]:
    return [e.alias for e in ENTRIES if e.alias.startswith(incomplete)]


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


@cli.command(name="list-exprs")
def list_exprs() -> None:
    """Print Python-importable expression names."""
    for py_name, alias in sorted(_ALIAS_MAP.items()):
        click.echo(f"{py_name:30s} -> {alias}")


@cli.command()
@click.argument("alias", shell_complete=_complete_alias)
@click.option("--limit", "-n", default=10, show_default=True, help="Rows to display.")
def run(alias: str, limit: int) -> None:
    """Execute an expression and print the first rows."""
    expr = load(alias)
    df = expr.limit(limit).to_pandas()
    click.echo(df.to_string())


@cli.command()
@click.argument("alias", shell_complete=_complete_alias)
def show(alias: str) -> None:
    """Show schema and metadata for a catalog entry."""
    expr = load(alias)
    schema = expr.schema()
    click.echo(f"Alias:   {alias}")
    click.echo(f"Type:    {type(expr).__name__}")
    click.echo(f"Columns: {len(schema.names)}")
    click.echo()
    for name, dtype in zip(schema.names, schema.types):
        click.echo(f"  {name:40s} {dtype}")


@cli.command()
def rebuild() -> None:
    """Wipe the submodule catalog and rebuild every entry from src/exprs/."""
    raise SystemExit(_rebuild())
