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

from semantic_bts._paths import SUBMODULE_PATH
from semantic_bts.api import _ALIAS_MAP, ENTRIES, catalog, load
from semantic_bts.api import rebuild as _rebuild


def _complete_alias(_ctx, _param, incomplete: str) -> list[str]:
    return [e.alias for e in ENTRIES if e.alias.startswith(incomplete)]


def _has_catalog() -> bool:
    return (SUBMODULE_PATH / "catalog.yaml").exists()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command(name="list")
def list_entries() -> None:
    """Print the aliases this package ships with."""
    if _has_catalog():
        cat = catalog()
        for entry in ENTRIES:
            try:
                handle = cat.load(entry.alias)
                kind = type(handle).__name__
            except Exception as exc:  # noqa: BLE001
                kind = f"<unloadable: {exc.__class__.__name__}>"
            click.echo(f"{entry.alias:30s} {kind}")
    else:
        click.echo("(catalog submodule not available — showing static entries)\n")
        for entry in ENTRIES:
            click.echo(f"{entry.alias:30s} {entry.expr_var}")


@cli.command(name="list-exprs")
def list_exprs() -> None:
    """Print Python-importable expression names."""
    for py_name, alias in sorted(_ALIAS_MAP.items()):
        click.echo(f"{py_name:30s} -> {alias}")


@cli.command()
@click.argument("alias", shell_complete=_complete_alias)
@click.option("--limit", "-n", default=10, show_default=True, help="Rows to display.")
@click.option(
    "--year-months",
    default=None,
    help='Comma-separated BTS months, e.g. "2025_10,2025_11". '
    "Omit for the default range.",
)
def run(alias: str, limit: int, year_months: str | None) -> None:
    """Execute an expression and print the first rows."""
    if not _has_catalog():
        raise click.ClickException(
            "catalog submodule not found — clone with --recurse-submodules to use 'run'"
        )
    expr = load(alias)
    params = {"year_months": year_months} if year_months else {}
    df = expr.limit(limit).to_pandas(params=params)
    click.echo(df.to_string())


@cli.command()
@click.argument("alias", shell_complete=_complete_alias)
def show(alias: str) -> None:
    """Show schema and metadata for a catalog entry."""
    if not _has_catalog():
        raise click.ClickException(
            "catalog submodule not found — clone with --recurse-submodules to use 'show'"
        )
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
    if not _has_catalog():
        raise click.ClickException(
            "catalog submodule not found — clone with --recurse-submodules to use 'rebuild'"
        )
    raise SystemExit(_rebuild())
