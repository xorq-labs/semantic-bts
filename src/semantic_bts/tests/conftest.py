"""Shared fixtures + skip-if-no-submodule guard."""

from __future__ import annotations

import pytest

from semantic_bts._paths import SUBMODULE_PATH


def pytest_collection_modifyitems(config, items):
    if (SUBMODULE_PATH / "catalog.yaml").exists():
        return
    skip = pytest.mark.skip(
        reason=f"submodule catalog not initialized at {SUBMODULE_PATH}; "
        f"run: git submodule update --init --recursive"
    )
    for item in items:
        item.add_marker(skip)
