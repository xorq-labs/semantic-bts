"""Metadata-only tests against the bundled catalog.

These tests deliberately avoid executing any expression — `cat.load(alias)`
only deserializes the expression tree, so nothing reaches bts.gov or the
parquet snapshot cache. If you want to exercise the fetch path, write a
`@pytest.mark.scripts` integration test.
"""

from __future__ import annotations

import pytest
from xorq.catalog.catalog import Catalog

from semantic_bts.api import ENTRIES, catalog, load


@pytest.mark.core
def test_catalog_opens():
    assert isinstance(catalog(), Catalog)


@pytest.mark.core
@pytest.mark.parametrize("entry", ENTRIES, ids=lambda e: e.alias)
def test_entry_loadable(entry):
    handle = load(entry.alias)
    assert handle is not None
    # every cataloged entry exposes a schema
    assert hasattr(handle, "schema")
    assert len(handle.schema().names) > 0


@pytest.mark.core
def test_flights_schema_has_provenance():
    schema = load("flights").schema()
    names = set(schema.names)
    # BTS canonical columns
    assert {"Year", "Quarter", "Month", "FlightDate", "Reporting_Airline"} <= names
    assert {"Origin", "Dest", "DepDelay", "ArrDelay"} <= names
    # provenance columns added by the UDXF
    assert {
        "_bts_year",
        "_bts_month",
        "_bts_source_file",
        "_bts_source_url_prefix",
    } <= names


@pytest.mark.core
def test_semantic_model_surface():
    builder = load("semantic-flights").ls.builder
    dims = set(builder.dimensions)
    measures = set(builder.measures)
    # spot-check each dimension group
    assert {"origin_state", "dest_state", "year", "month", "reporting_airline"} <= dims
    # measures we use in the aggregates
    assert {
        "n_flights",
        "avg_dep_delay",
        "avg_arr_delay",
        "dep_delay_pct_block",
        "arr_delay_pct_block",
    } <= measures


@pytest.mark.core
@pytest.mark.parametrize(
    "alias,expected_cols",
    [
        (
            "flights-by-month-od-state",
            {"month", "origin_state", "dest_state", "n_flights", "avg_dep_delay"},
        ),
        (
            "flights-by-quarter-carrier",
            {"quarter", "reporting_airline", "n_flights", "avg_dep_delay"},
        ),
        (
            "flights-by-dow-deststate",
            {"day_of_week", "dest_state_name", "n_flights", "avg_dep_delay"},
        ),
    ],
)
def test_aggregate_schemas(alias, expected_cols):
    assert expected_cols <= set(load(alias).schema().names)
