"""CLI plumbing tests (no expression execution, no network)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from semantic_bts.api import _ALIAS_MAP, ENTRIES
from semantic_bts.cli import cli


@pytest.mark.core
def test_cli_help_lists_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("list", "list-exprs", "run", "show", "rebuild"):
        assert cmd in result.output


@pytest.mark.core
def test_cli_list_prints_every_alias():
    result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 0, result.output
    for entry in ENTRIES:
        assert entry.alias in result.output


@pytest.mark.core
def test_cli_list_exprs_prints_python_names():
    result = CliRunner().invoke(cli, ["list-exprs"])
    assert result.exit_code == 0, result.output
    for py_name in _ALIAS_MAP:
        assert py_name in result.output


@pytest.mark.core
def test_cli_show_prints_schema():
    result = CliRunner().invoke(cli, ["show", "flights"])
    assert result.exit_code == 0, result.output
    assert "Alias:" in result.output
    assert "flights" in result.output
    assert "Columns:" in result.output


@pytest.mark.scripts
def test_cli_run_prints_rows():
    result = CliRunner().invoke(cli, ["run", "flights", "--limit", "3"])
    assert result.exit_code == 0, result.output
    assert len(result.output.strip().splitlines()) > 1
