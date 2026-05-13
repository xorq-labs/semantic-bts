"""Build script: `semantic-flights` BSL semantic model over the `flights` entry.

Top-level binding: expr
"""

from boring_semantic_layer import Dimension, Measure, SemanticModel
from xorq.catalog.catalog import Catalog

from semantic_bts._paths import SUBMODULE_PATH


cat = Catalog.from_repo_path(str(SUBMODULE_PATH))
flights = cat.load("flights")


# Dimension groups: exposed via naming convention so downstream consumers
# can iterate the model.dimensions dict and filter by prefix.
ORIGIN_DIMS = (
    "origin_code",
    "origin_city",
    "origin_state",
    "origin_state_name",
)
DEST_DIMS = (
    "dest_code",
    "dest_city",
    "dest_state",
    "dest_state_name",
)
TIME_DIMS = (
    "year",
    "quarter",
    "month",
    "day_of_week",
    "dep_time_blk",
    "arr_time_blk",
)
CARRIER_DIMS = (
    "reporting_airline",
    "iata_carrier",
)


model = SemanticModel(
    table=flights,
    name="flights_semantic",
    dimensions={
        # origin
        "origin_code": Dimension(expr=lambda t: t.Origin),
        "origin_city": Dimension(expr=lambda t: t.OriginCityName),
        "origin_state": Dimension(expr=lambda t: t.OriginState),
        "origin_state_name": Dimension(expr=lambda t: t.OriginStateName),
        # destination
        "dest_code": Dimension(expr=lambda t: t.Dest),
        "dest_city": Dimension(expr=lambda t: t.DestCityName),
        "dest_state": Dimension(expr=lambda t: t.DestState),
        "dest_state_name": Dimension(expr=lambda t: t.DestStateName),
        # time
        "year": Dimension(expr=lambda t: t.Year),
        "quarter": Dimension(expr=lambda t: t.Quarter),
        "month": Dimension(expr=lambda t: t.Month),
        "day_of_week": Dimension(expr=lambda t: t.DayOfWeek),
        "dep_time_blk": Dimension(expr=lambda t: t.DepTimeBlk),
        "arr_time_blk": Dimension(expr=lambda t: t.ArrTimeBlk),
        # carrier
        "reporting_airline": Dimension(expr=lambda t: t.Reporting_Airline),
        "iata_carrier": Dimension(expr=lambda t: t.IATA_CODE_Reporting_Airline),
    },
    measures={
        "n_flights": Measure(expr=lambda t: t.count()),
        "avg_dep_delay": Measure(expr=lambda t: t.DepDelay.mean()),
        "avg_arr_delay": Measure(expr=lambda t: t.ArrDelay.mean()),
        "avg_dep_delay_minutes": Measure(expr=lambda t: t.DepDelayMinutes.mean()),
        "avg_arr_delay_minutes": Measure(expr=lambda t: t.ArrDelayMinutes.mean()),
        # delay as % of actual gate-to-gate block time
        # (TaxiOut + AirTime + TaxiIn == ActualElapsedTime in BTS)
        "dep_delay_pct_block": Measure(
            expr=lambda t: t.DepDelay.sum() / t.ActualElapsedTime.sum() * 100
        ),
        "arr_delay_pct_block": Measure(
            expr=lambda t: t.ArrDelay.sum() / t.ActualElapsedTime.sum() * 100
        ),
    },
)

# `flights` is already cached upstream, so the semantic model is left uncached.
expr = model.to_tagged()
