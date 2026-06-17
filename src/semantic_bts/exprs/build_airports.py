"""Build script: `airports` catalog entry — BTS L_AIRPORT_ID lookup.

Maps the numeric airport id carried in `flights` (`OriginAirportID` /
`DestAirportID`) to a "City, ST: Airport Name" label. Fetched live from the
BTS TranStats lookup endpoint, mirroring the `flights` source pattern.

Top-level binding: expr
"""

import xorq.api as xo
from xorq.expr.relations import flight_udxf


def fetch_airports(df_in):
    """UDXF body: download the L_AIRPORT_ID lookup CSV (Code,Description).

    ``Code`` is the numeric airport id (cast to int64 to match the int64
    OriginAirportID/DestAirportID join keys in `flights`). ``df_in`` is an
    ignored 1-row trigger.
    """
    import io
    import urllib.error
    import urllib.request

    import pandas as pd
    import pyarrow as pa

    # ROT13-obfuscated TranStats token resolving to L_AIRPORT_ID.
    URL = "https://www.transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_NVecbeg_VQ"

    req = urllib.request.Request(URL, headers={"User-Agent": "xorq-catalog-bts/1.0"})
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                raw = r.read()
            break
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
    else:
        raise RuntimeError(f"airport lookup download failed: {last}")

    df = pd.read_csv(
        io.BytesIO(raw),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        encoding="latin-1",
    )
    out = pd.DataFrame(
        {
            "airport_id": pd.to_numeric(df["Code"], errors="coerce").astype("Int64"),
            "airport_name": df["Description"].astype("string"),
            "_bts_source_url": URL,
        }
    )
    out = out.dropna(subset=["airport_id"]).drop_duplicates("airport_id")
    out = out.sort_values("airport_id", kind="mergesort").reset_index(drop=True)

    target_schema = pa.schema(
        [
            ("airport_id", pa.int64()),
            ("airport_name", pa.string()),
            ("_bts_source_url", pa.string()),
        ]
    )
    table = pa.Table.from_pandas(out, preserve_index=False).cast(
        target_schema, safe=False
    )
    return table.to_pandas(types_mapper=pd.ArrowDtype)


con = xo.connect()

# Mirror the `flights` source input shape (see build_carriers.py): a literal
# projected onto a 1-row table, so the column survives build-artifact
# serialization when this source is embedded under a join.
trigger = xo.memtable({"_": [0]}).select(trigger=xo.literal(0).cast("int64"))
schema_in = xo.schema({"trigger": "int64"})
schema_out = xo.schema(
    {
        "airport_id": "int64",
        "airport_name": "string",
        "_bts_source_url": "string",
    }
)

# NOT cached (see build_carriers.py): small lookup, and an uncached UDXF
# embeds cleanly in the cross-backend join_one used by the enrichment example.
expr = flight_udxf(
    trigger,
    process_df=fetch_airports,
    maybe_schema_in=schema_in,
    maybe_schema_out=schema_out,
    con=con,
    make_udxf_kwargs={"name": "fetch_airports"},
)
