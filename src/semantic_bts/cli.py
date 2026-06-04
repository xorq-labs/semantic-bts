"""The `semantic-bts` CLI.

This package's job is to demonstrate xorq, not to wrap it. For every catalog
operation (`list`, `show`, `run`, `tui`, `add`, `remove`, ...) use `xorq` directly:

    xorq catalog -p xorq-catalog-bts list
    xorq catalog -p xorq-catalog-bts run flights -o - -f json --limit 5

The one project-specific command is `rebuild`, which has no `xorq` equivalent:
it wipes the submodule catalog and rebuilds every entry from `src/exprs/`.
"""

from __future__ import annotations

import click

from semantic_bts._paths import SUBMODULE_PATH
from semantic_bts.api import rebuild as _rebuild


def _has_catalog() -> bool:
    return (SUBMODULE_PATH / "catalog.yaml").exists()


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx) -> None:
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
def rebuild() -> None:
    """Wipe the submodule catalog and rebuild every entry from src/exprs/."""
    if not _has_catalog():
        raise click.ClickException(
            "catalog submodule not found — clone with --recurse-submodules to use 'rebuild'"
        )
    raise SystemExit(_rebuild())
