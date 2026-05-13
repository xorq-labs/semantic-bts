"""Build script: aggregate by (day_of_week, dest_state_name).

Top-level binding: expr_dow_deststate
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

expr_dow_deststate = model.query(
    dimensions=["day_of_week", "dest_state_name"],
    measures=MEASURES,
    order_by=[("day_of_week", "asc"), ("avg_dep_delay", "desc")],
).to_untagged()
