"""Build scripts: BSL join examples over `flights` + `carriers`/`airports` dims.

Demonstrates how the semantic layer protects additive measures from the
classic BI join traps. Three top-level expression bindings, each catalogued
as its own entry:

  expr_enriched  -- join_one: flights enriched with real carrier/airport NAMES
                    (the flights CSV carries only codes). A "diamond"/convergent
                    join_one to the airports lookup on both origin and dest does
                    NOT fan out — row count and measures stay correct.

  expr_fanout    -- join_many FAN-OUT: a one-row-per-carrier parent fact
                    (`carrier_budget`, additive `monthly_budget`) joined to the
                    many individual flights. A naive SQL join would repeat the
                    budget once per flight and inflate SUM(monthly_budget); BSL
                    pre-aggregates the parent at its own grain, so the total
                    stays correct.

  expr_chasm     -- join_many CHASM: two many-arms off the carrier dimension
                    (flights AND `carrier_incidents`). A naive join produces the
                    flights x incidents cross-product per carrier, inflating BOTH
                    SUM(n_flights) and SUM(cost); BSL aggregates each arm on its
                    own raw table, so both totals stay correct.

The carrier/airport dimension tables are REAL BTS lookups (`carriers`,
`airports`). The `carrier_budget` / `carrier_incidents` facts are CONTRIVED
illustrative data: their measure *values* are synthetic, but they are derived
from the real carrier keys so every carrier present in `flights` is covered.
(BTS does publish a real second fact — T-100 segment passengers/seats — but it
is only available as a dynamically generated, randomly-named download, unfit
for a reproducible catalog UDXF, so contrived facts stand in here.)

Top-level bindings: expr_enriched, expr_fanout, expr_chasm
"""

import xorq.api as xo
from boring_semantic_layer import Dimension, Measure, SemanticModel
from xorq.catalog.catalog import Catalog
from xorq.expr.relations import flight_udxf
from xorq.vendor.ibis import _

from semantic_bts._paths import SUBMODULE_PATH
from semantic_bts.exprs.build_airports import fetch_airports
from semantic_bts.exprs.build_carriers import fetch_carriers


cat = Catalog.from_repo_path(str(SUBMODULE_PATH))

# --- real sources -----------------------------------------------------------
# Project flights so the carrier join key shares the column NAME used by the
# dimension/fact tables (`carrier_code`); BSL's string-keyed joins resolve raw
# columns, so the name must match on both sides.
flights_src = cat.load("flights")
# `_con` IS the flights backend — the single engine instance the flights expr
# is bound to. Everything joined below is put on this same engine so every join
# is single-engine: no cross-backend RemoteTable bridges, so the build artifact
# round-trips through `xorq catalog run`.
_con = flights_src._find_backend()
flights_tbl = flights_src.mutate(carrier_code=_.Reporting_Airline)

# The `carriers`/`airports` catalog entries live on their OWN backends, so
# join_one to them would be cross-backend (works in-process, but the isolated
# catalog runner can't replay the bridge). Instead we fetch the same lookups
# directly onto `_con` via their UDXFs — same data, single engine.
_trigger = xo.memtable({"_": [0]}).select(trigger=xo.literal(0).cast("int64"))
_schema_in = xo.schema({"trigger": "int64"})
carriers_tbl = flight_udxf(
    _trigger,
    process_df=fetch_carriers,
    maybe_schema_in=_schema_in,
    maybe_schema_out=xo.schema(
        {"carrier_code": "string", "carrier_name": "string", "_bts_source_url": "string"}
    ),
    con=_con,
    make_udxf_kwargs={"name": "fetch_carriers"},
)
airports_tbl = flight_udxf(
    _trigger,
    process_df=fetch_airports,
    maybe_schema_in=_schema_in,
    maybe_schema_out=xo.schema(
        {"airport_id": "int64", "airport_name": "string", "_bts_source_url": "string"}
    ),
    con=_con,
    make_udxf_kwargs={"name": "fetch_airports"},
)

# --- contrived carrier facts (synthetic measures, real keys) ----------------
# Derived from `flights` (NOT the carriers lookup) so every join_many input
# shares the flights backend: join_many's pre-aggregation spans both arms in
# one SQL plan and rejects a multi-backend expr, whereas the cross-backend
# join_one to the real lookups below is fine.
carrier_spine = flights_tbl.select(carrier_code=_.carrier_code).distinct()
# One row per carrier, additive monthly_budget — the FAN-OUT parent measure.
carrier_budget_tbl = carrier_spine.mutate(
    monthly_budget=(_.carrier_code.length() * 1000).cast("int64")
)
# Two rows per carrier (cost 100 + 50), a genuine many-side — the CHASM 2nd arm.
carrier_incidents_tbl = carrier_spine.mutate(cost=_.carrier_code.length() + 100).union(
    carrier_spine.mutate(cost=_.carrier_code.length() + 50)
)

# --- semantic models --------------------------------------------------------
flights = SemanticModel(
    table=flights_tbl,
    name="flights",
    dimensions={
        "carrier_code": Dimension(expr=lambda t: t.carrier_code),
        "origin_id": Dimension(expr=lambda t: t.OriginAirportID),
        "dest_id": Dimension(expr=lambda t: t.DestAirportID),
        "month": Dimension(expr=lambda t: t.Month),
    },
    measures={
        "n_flights": Measure(expr=lambda t: t.count()),
        "avg_dep_delay": Measure(expr=lambda t: t.DepDelay.mean()),
        "avg_arr_delay": Measure(expr=lambda t: t.ArrDelay.mean()),
        "total_distance": Measure(expr=lambda t: t.Distance.sum()),
    },
)

carriers = SemanticModel(
    table=carriers_tbl,
    name="carriers",
    dimensions={
        "carrier_code": Dimension(expr=lambda t: t.carrier_code),
        "carrier_name": Dimension(expr=lambda t: t.carrier_name),
    },
)

airports = SemanticModel(
    table=airports_tbl,
    name="airports",
    dimensions={
        "airport_id": Dimension(expr=lambda t: t.airport_id),
        "airport_name": Dimension(expr=lambda t: t.airport_name),
    },
)

carrier_spine_model = SemanticModel(
    table=carrier_spine,
    name="carrier_spine",
    dimensions={"carrier_code": Dimension(expr=lambda t: t.carrier_code)},
    measures={"n_carriers": Measure(expr=lambda t: t.count())},
)

carrier_budget = SemanticModel(
    table=carrier_budget_tbl,
    name="carrier_budget",
    dimensions={"carrier_code": Dimension(expr=lambda t: t.carrier_code)},
    measures={"total_budget": Measure(expr=lambda t: t.monthly_budget.sum())},
)

carrier_incidents = SemanticModel(
    table=carrier_incidents_tbl,
    name="carrier_incidents",
    dimensions={"carrier_code": Dimension(expr=lambda t: t.carrier_code)},
    measures={"total_cost": Measure(expr=lambda t: t.cost.sum())},
)

# --- (1) join_one enrichment (diamond on the airports lookup) ---------------
expr_enriched = (
    flights.join_one(carriers, on="carrier_code")
    .join_one(airports, on=lambda f, a: f.OriginAirportID == a.airport_id)
    .group_by("carriers.carrier_name", "airports.airport_name")
    .aggregate("flights.n_flights", "flights.avg_dep_delay", "flights.avg_arr_delay")
    .to_untagged()
)

# --- (2) join_many FAN-OUT protection ---------------------------------------
expr_fanout = (
    carrier_budget.join_many(flights, on="carrier_code")
    .group_by("carrier_budget.carrier_code")
    .aggregate("carrier_budget.total_budget", "flights.n_flights")
    .to_untagged()
)

# --- (3) join_many CHASM protection -----------------------------------------
# Parent is the flights-backed carrier spine (so both join_many arms share the
# flights backend); group by carrier_code. The real carrier NAME is shown by
# the enrichment example above instead.
expr_chasm = (
    carrier_spine_model.join_many(flights, on="carrier_code")
    .join_many(carrier_incidents, on="carrier_code")
    .group_by("carrier_spine.carrier_code")
    .aggregate("flights.n_flights", "carrier_incidents.total_cost")
    .to_untagged()
)
