"""CLI plumbing tests (no expression execution, no network)."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from semantic_bts.api import ENTRIES
from semantic_bts.cli import cli


@pytest.mark.core
def test_cli_help_lists_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "rebuild" in result.output


@pytest.mark.core
def test_cli_list_prints_every_alias():
    result = CliRunner().invoke(cli, ["list"])
    assert result.exit_code == 0, result.output
    for entry in ENTRIES:
        assert entry.alias in result.output
