import runpy
import subprocess

import pytest

import semantic_bts_demo


@pytest.mark.core
@pytest.mark.parametrize(
    "modname,expected,run_name",
    (
        ("semantic_bts_demo", "Hello from semantic-bts-demo package!", "__main__"),
        ("semantic_bts_demo.hello", "Hello from semantic-bts-demo.hello!", "__main__"),
    ),
)
def test_module_imports(modname, expected, run_name, capsys):
    runpy.run_module(modname, run_name=run_name)
    captured = capsys.readouterr()
    assert captured.out == f"{expected}\n", (captured.out, expected)
    assert captured.err == ""


@pytest.mark.core
def test_hello(capsys):
    semantic_bts_demo.hello.hello()
    captured = capsys.readouterr()
    expected = "Hello from semantic-bts-demo.hello:hello!"
    assert captured.out == f"{expected}\n", (captured.out, expected)
    assert captured.err == ""


@pytest.mark.scripts
def test_hello_script(capsys):
    actual = subprocess.check_output("semantic-bts-demo-function")
    expected = b"Hello from semantic-bts-demo.hello:hello!\n"
    assert actual == expected, (actual, expected)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
