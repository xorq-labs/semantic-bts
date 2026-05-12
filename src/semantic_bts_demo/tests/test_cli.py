import subprocess

import pytest
from click.testing import CliRunner

from semantic_bts_demo.cli import cli


@pytest.mark.core
@pytest.mark.parametrize(
    "args,expected",
    (
        (["hello"], "Hello, world!\n"),
        (["hello", "world"], "Hello, world!\n"),
        (["hello", "Alice"], "Hello, Alice!\n"),
        ([], "Hello, world!\n"),
        (["Alice"], "Hello, Alice!\n"),
    ),
)
def test_hello(args, expected):
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0
    assert result.output == expected


@pytest.mark.scripts
@pytest.mark.parametrize(
    "args,expected",
    (
        ([], b"Hello, world!\n"),
        (["Alice"], b"Hello, Alice!\n"),
        (["hello", "Alice"], b"Hello, Alice!\n"),
    ),
)
def test_hello_script(args, expected):
    actual = subprocess.check_output(["semantic-bts-demo", *args])
    assert actual == expected
