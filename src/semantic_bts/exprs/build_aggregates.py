"""Build script: two BSL aggregate catalog entries derived from `semantic-flights`.

Top-level bindings:
  expr_month_od    -- monthly metrics by (origin_state, dest_state)
  expr_quarter_car -- quarterly metrics by reporting_airline
"""

from xorq.catalog.catalog import Catalog

from semantic_bts._paths import SUBMODULE_PATH


cat = Catalog.from_repo_path(str(SUBMODULE_PATH))
model = cat.load("semantic-flights").ls.builder

MEASURES = [
    "n_flights",
    "avg_dep_delay",
    "avg_arr_delay",
    "dep_delay_pct_block",
    "arr_delay_pct_block",
]

expr_month_od = model.query(
    dimensions=["month", "origin_state", "dest_state"],
    measures=MEASURES,
    order_by=[("month", "asc"), ("avg_dep_delay", "desc")],
).to_untagged()

expr_quarter_car = model.query(
    dimensions=["quarter", "reporting_airline"],
    measures=MEASURES,
    order_by=[("quarter", "asc"), ("avg_dep_delay", "desc")],
).to_untagged()
