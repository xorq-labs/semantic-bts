"""Build scripts: BSL join examples built ON the catalogued `semantic-flights`.

Recovers the published `flights_semantic` model from the catalog
(`cat.load("semantic-flights").ls.builder`) and anchors on its underlying table,
so the lineage stays tied to the published model instead of re-loading `flights`
directly. A small join-ready fact model is built over that table for the joins
(joining the recovered model directly is avoided — it carries 14 dims / 8
measures the examples don't need, and a freshly-scoped model keeps the join keys
and prefixes clean). Three top-level expression bindings, each catalogued as its
own entry:

  expr_enriched  -- join_one: flights enriched with real carrier/airport NAMES
                    (the flights CSV carries only codes). Each flight maps to
                    exactly one carrier and one origin airport, so join_one does
                    NOT fan out — row count and measures stay correct. This is
                    the "safe join" baseline.

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

Everything is kept on the `semantic-flights` model's own (single) backend so the
build artifacts round-trip through `xorq catalog run`: the contrived facts are
derived from the model's underlying table, and the carrier/airport name lookups
are fetched onto that same backend (a cross-backend join can't be replayed by
the isolated runner).

The carrier/airport names come from REAL BTS lookups (L_UNIQUE_CARRIERS /
L_AIRPORT_ID, the same data as the `carriers`/`airports` source entries). The
`carrier_budget` / `carrier_incidents` facts are CONTRIVED: their measure
*values* are synthetic, but they are keyed on the real carrier codes present in
`flights`. (BTS does publish a real second fact — T-100 segment passengers/seats
— but only as a dynamically generated, randomly-named download, unfit for a
reproducible catalog UDXF, so contrived facts stand in here.)

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

# Anchor on the PUBLISHED semantic model: recover `flights_semantic` from the
# catalog and take its underlying table as the lineage root (rather than
# re-loading `flights` directly). We build a small join-ready model over that
# table — a freshly-constructed model is required because a *recovered*
# SemanticModel returns NaN measures when used directly as a join_many arm
# (BSL pre-agg round-trip limitation); join_one on the recovered model is fine.
semantic_flights = cat.load("semantic-flights").ls.builder

# Project the published table so the carrier join key has a clean shared NAME
# (`carrier_code`); BSL's string-keyed joins resolve raw columns, so the name
# must match on both sides.
flights_tbl = semantic_flights.table.mutate(carrier_code=_.Reporting_Airline)
# `_con` is that table's backend — the single engine instance it is bound to.
# Everything joined below is placed on this same engine so each join is
# single-engine: no cross-backend RemoteTable bridges, so the build artifact
# round-trips through `xorq catalog run`.
_con = flights_tbl._find_backend()

# --- real name lookups, fetched onto the model's backend --------------------
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
# Derived from the published model's table so they share its backend, keyed on
# the shared `carrier_code` column (BSL's string-keyed join_many resolves raw
# columns, so the name must match on every arm).
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
# Fresh join-ready fact model over the published `flights_semantic` table.
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

# --- (1) join_one enrichment (safe many-to-one lookup) ----------------------
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
# Two many-arms (flights AND carrier_incidents) off the carrier spine; group by
# carrier_code. The real carrier NAME is shown by the enrichment example above.
expr_chasm = (
    carrier_spine_model.join_many(flights, on="carrier_code")
    .join_many(carrier_incidents, on="carrier_code")
    .group_by("carrier_spine.carrier_code")
    .aggregate("flights.n_flights", "carrier_incidents.total_cost")
    .to_untagged()
)
