"""End-to-end execution tests.

These actually run expressions, so the first invocation on a fresh checkout
will hit https://transtats.bts.gov to populate the parquet snapshot cache.
Subsequent runs reuse the cache.

Marked `scripts` so they're skipped by `pytest -m core`. CI runs the full
suite (no marker filter), so they execute there.
"""

from __future__ import annotations

import pytest

from semantic_bts.api import ENTRIES, load


@pytest.mark.scripts
@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.alias)
def test_entry_count_positive(entry):
    """Every cataloged table has rows once executed end-to-end."""
    n = load(entry.alias).count().execute()
    assert n > 0, f"{entry.alias} produced 0 rows"
