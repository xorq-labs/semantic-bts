"""Build script: `carriers` catalog entry — BTS L_UNIQUE_CARRIERS lookup.

A dimension/lookup source: maps the carrier code carried in `flights`
(`Reporting_Airline`) to a human-readable airline name, which the flights
CSV does NOT contain. Fetched live from the BTS TranStats lookup endpoint,
mirroring the `flights` source pattern (UDXF + ParquetSnapshotCache).

Top-level binding: expr
"""

import xorq.api as xo
from xorq.expr.relations import flight_udxf


def fetch_carriers(df_in):
    """UDXF body: download the L_UNIQUE_CARRIERS lookup CSV (Code,Description).

    All imports/constants are LOCAL so cloudpickle round-trips cleanly when
    the build script is off the import path. ``df_in`` is an ignored 1-row
    trigger; the lookup URL is fixed.
    """
    import urllib.error
    import urllib.request

    import pandas as pd
    import pyarrow as pa

    # BTS TranStats Download_Lookup tokens are ROT13-obfuscated; this token
    # resolves to L_UNIQUE_CARRIERS (verified to return a Code,Description CSV).
    URL = "https://www.transtats.bts.gov/Download_Lookup.asp?Y11x72=Y_haVdhR_PNeeVRef"

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
        raise RuntimeError(f"carrier lookup download failed: {last}")

    import io

    df = pd.read_csv(
        io.BytesIO(raw),
        dtype=str,
        keep_default_na=False,
        na_values=[""],
        encoding="latin-1",
    )
    out = pd.DataFrame(
        {
            "carrier_code": df["Code"].astype("string"),
            "carrier_name": df["Description"].astype("string"),
            "_bts_source_url": URL,
        }
    )
    out = out.dropna(subset=["carrier_code"]).drop_duplicates("carrier_code")
    out = out.sort_values("carrier_code", kind="mergesort").reset_index(drop=True)

    target_schema = pa.schema(
        [
            ("carrier_code", pa.string()),
            ("carrier_name", pa.string()),
            ("_bts_source_url", pa.string()),
        ]
    )
    table = pa.Table.from_pandas(out, preserve_index=False).cast(
        target_schema, safe=False
    )
    return table.to_pandas(types_mapper=pd.ArrowDtype)


con = xo.connect()

# Mirror the `flights` source input shape: a literal projected onto a 1-row
# table. A bare memtable({"trigger": [0]}) round-trips fine standalone but
# loses its column when the build artifact is embedded under a join, so we use
# the same select-a-literal construction that the flights UDXF input uses.
trigger = xo.memtable({"_": [0]}).select(trigger=xo.literal(0).cast("int64"))
schema_in = xo.schema({"trigger": "int64"})
schema_out = xo.schema(
    {
        "carrier_code": "string",
        "carrier_name": "string",
        "_bts_source_url": "string",
    }
)

# NOT cached: the lookup is ~1.8k rows, so recomputing per run is cheap, and a
# ParquetSnapshotCache snapshot can't be resolved when this source is embedded
# in a cross-backend join_one (the isolated runner can't find the snapshot
# table). The raw UDXF embeds cleanly instead.
expr = flight_udxf(
    trigger,
    process_df=fetch_carriers,
    maybe_schema_in=schema_in,
    maybe_schema_out=schema_out,
    con=con,
    make_udxf_kwargs={"name": "fetch_carriers"},
)
