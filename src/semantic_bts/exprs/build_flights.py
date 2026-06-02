"""Build script: `flights` catalog entry sourced from BTS On-Time CSVs.

Top-level binding:  expr  (a xorq expression)
"""

import xorq.api as xo
from xorq.caching import ParquetSnapshotCache
from xorq.expr.relations import flight_udxf


def fetch_bts_months(df_in):
    """UDXF body: download BTS On-Time monthly zips, parse CSVs, concat, cast.

    All imports and large constants are LOCAL so cloudpickle round-trips
    cleanly when the build script is no longer on the import path.
    """
    import io
    import urllib.error
    import urllib.request
    import zipfile

    import pandas as pd
    import pyarrow as pa

    URL_TEMPLATE = (
        "https://transtats.bts.gov/PREZIP/"
        "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year_month}.zip"
    )

    # Canonical BTS On-Time Reporting Carrier On-Time Performance schema.
    # Column order matches the published CSV header for 2025-era files.
    # Provenance columns are appended.
    BTS_FIELDS = [
        # calendar
        ("Year", pa.int32()),
        ("Quarter", pa.int32()),
        ("Month", pa.int32()),
        ("DayofMonth", pa.int32()),
        ("DayOfWeek", pa.int32()),
        ("FlightDate", pa.date32()),
        # carrier identity
        ("Reporting_Airline", pa.string()),
        ("DOT_ID_Reporting_Airline", pa.int64()),
        ("IATA_CODE_Reporting_Airline", pa.string()),
        ("Tail_Number", pa.string()),
        ("Flight_Number_Reporting_Airline", pa.int64()),
        # origin
        ("OriginAirportID", pa.int64()),
        ("OriginAirportSeqID", pa.int64()),
        ("OriginCityMarketID", pa.int64()),
        ("Origin", pa.string()),
        ("OriginCityName", pa.string()),
        ("OriginState", pa.string()),
        ("OriginStateFips", pa.int32()),
        ("OriginStateName", pa.string()),
        ("OriginWac", pa.int32()),
        # dest
        ("DestAirportID", pa.int64()),
        ("DestAirportSeqID", pa.int64()),
        ("DestCityMarketID", pa.int64()),
        ("Dest", pa.string()),
        ("DestCityName", pa.string()),
        ("DestState", pa.string()),
        ("DestStateFips", pa.int32()),
        ("DestStateName", pa.string()),
        ("DestWac", pa.int32()),
        # departure perf
        ("CRSDepTime", pa.int32()),
        ("DepTime", pa.int32()),
        ("DepDelay", pa.float64()),
        ("DepDelayMinutes", pa.float64()),
        ("DepDel15", pa.float64()),
        ("DepartureDelayGroups", pa.int32()),
        ("DepTimeBlk", pa.string()),
        ("TaxiOut", pa.float64()),
        ("WheelsOff", pa.int32()),
        ("WheelsOn", pa.int32()),
        ("TaxiIn", pa.float64()),
        # arrival perf
        ("CRSArrTime", pa.int32()),
        ("ArrTime", pa.int32()),
        ("ArrDelay", pa.float64()),
        ("ArrDelayMinutes", pa.float64()),
        ("ArrDel15", pa.float64()),
        ("ArrivalDelayGroups", pa.int32()),
        ("ArrTimeBlk", pa.string()),
        # cancellation / diversion
        ("Cancelled", pa.float64()),
        ("CancellationCode", pa.string()),
        ("Diverted", pa.float64()),
        # durations
        ("CRSElapsedTime", pa.float64()),
        ("ActualElapsedTime", pa.float64()),
        ("AirTime", pa.float64()),
        ("Flights", pa.float64()),
        ("Distance", pa.float64()),
        ("DistanceGroup", pa.int32()),
        # delay reasons
        ("CarrierDelay", pa.float64()),
        ("WeatherDelay", pa.float64()),
        ("NASDelay", pa.float64()),
        ("SecurityDelay", pa.float64()),
        ("LateAircraftDelay", pa.float64()),
        # gate-return / diversion summary
        ("FirstDepTime", pa.int32()),
        ("TotalAddGTime", pa.float64()),
        ("LongestAddGTime", pa.float64()),
        ("DivAirportLandings", pa.int32()),
        ("DivReachedDest", pa.float64()),
        ("DivActualElapsedTime", pa.float64()),
        ("DivArrDelay", pa.float64()),
        ("DivDistance", pa.float64()),
        # Div1..Div5 blocks (Airport, AirportID, AirportSeqID,
        #   WheelsOn, TotalGTime, LongestGTime, WheelsOff, TailNum)
        ("Div1Airport", pa.string()),
        ("Div1AirportID", pa.int64()),
        ("Div1AirportSeqID", pa.int64()),
        ("Div1WheelsOn", pa.int32()),
        ("Div1TotalGTime", pa.float64()),
        ("Div1LongestGTime", pa.float64()),
        ("Div1WheelsOff", pa.int32()),
        ("Div1TailNum", pa.string()),
        ("Div2Airport", pa.string()),
        ("Div2AirportID", pa.int64()),
        ("Div2AirportSeqID", pa.int64()),
        ("Div2WheelsOn", pa.int32()),
        ("Div2TotalGTime", pa.float64()),
        ("Div2LongestGTime", pa.float64()),
        ("Div2WheelsOff", pa.int32()),
        ("Div2TailNum", pa.string()),
        ("Div3Airport", pa.string()),
        ("Div3AirportID", pa.int64()),
        ("Div3AirportSeqID", pa.int64()),
        ("Div3WheelsOn", pa.int32()),
        ("Div3TotalGTime", pa.float64()),
        ("Div3LongestGTime", pa.float64()),
        ("Div3WheelsOff", pa.int32()),
        ("Div3TailNum", pa.string()),
        ("Div4Airport", pa.string()),
        ("Div4AirportID", pa.int64()),
        ("Div4AirportSeqID", pa.int64()),
        ("Div4WheelsOn", pa.int32()),
        ("Div4TotalGTime", pa.float64()),
        ("Div4LongestGTime", pa.float64()),
        ("Div4WheelsOff", pa.int32()),
        ("Div4TailNum", pa.string()),
        ("Div5Airport", pa.string()),
        ("Div5AirportID", pa.int64()),
        ("Div5AirportSeqID", pa.int64()),
        ("Div5WheelsOn", pa.int32()),
        ("Div5TotalGTime", pa.float64()),
        ("Div5LongestGTime", pa.float64()),
        ("Div5WheelsOff", pa.int32()),
        ("Div5TailNum", pa.string()),
        # provenance
        ("_bts_year", pa.int32()),
        ("_bts_month", pa.int32()),
        ("_bts_source_file", pa.string()),
        ("_bts_source_url_prefix", pa.string()),
    ]
    target_schema = pa.schema(BTS_FIELDS)
    URL_PREFIX = "https://transtats.bts.gov/PREZIP/"

    def fetch_one(year_month):
        req = urllib.request.Request(
            URL_TEMPLATE.format(year_month=year_month),
            headers={"User-Agent": "xorq-catalog-bts/1.0"},
        )
        last = None
        for _ in range(3):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    zb = r.read()
                break
            except (urllib.error.URLError, TimeoutError) as e:
                last = e
        else:
            raise RuntimeError(f"download failed for {year_month}: {last}")
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            csv_name = max(
                (n for n in zf.namelist() if n.lower().endswith(".csv")),
                key=lambda n: zf.getinfo(n).file_size,
            )
            with zf.open(csv_name) as fh:
                return pd.read_csv(
                    fh,
                    dtype=str,
                    keep_default_na=False,
                    na_values=[""],
                    low_memory=False,
                    encoding="latin-1",
                )

    frames = []
    year_months = [
        part.strip()
        for cell in df_in["year_months"]
        for part in str(cell).split(",")
        if part.strip()
    ]
    for year_month in year_months:
        ys, ms = year_month.split("_", 1)
        year, month = int(ys), int(ms)
        df_m = fetch_one(year_month)
        df_m["_bts_year"] = year
        df_m["_bts_month"] = month
        df_m["_bts_source_file"] = (
            f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year_month}.zip"
        )
        df_m["_bts_source_url_prefix"] = URL_PREFIX
        frames.append(df_m)

    out = pd.concat(frames, ignore_index=True, sort=False)
    out = out.sort_values(
        [
            "_bts_year",
            "_bts_month",
            "FlightDate",
            "Reporting_Airline",
            "Flight_Number_Reporting_Airline",
            "Tail_Number",
        ],
        kind="mergesort",
        na_position="last",
    ).reset_index(drop=True)

    for col in target_schema.names:
        if col not in out.columns:
            out[col] = pd.NA
    out = out[target_schema.names]
    table = pa.Table.from_pandas(out, preserve_index=False).cast(
        target_schema, safe=False
    )
    return table.to_pandas(types_mapper=pd.ArrowDtype)


con = xo.connect()

# Deferred, comma-delimited month range re-pointable at execution time via
# params={"year_months": ...}; the default preserves the original range.
# The coalesce is a hash-time workaround for xorq-labs/xorq#2037: the dasher's
# content-hash replaces a NamedScalarParameter with an aliased literal
# placeholder, and a Project rejects a bare Alias as a column value. Wrapping
# the param keeps the Alias nested as an argument instead. The "" fallback is
# inert (the param always resolves non-null). Remove once #2037 is fixed.
months_input = xo.memtable({"_": [0]}).select(
    year_months=xo.coalesce(
        xo.param("year_months", "string", default="2025_11,2025_12"), ""
    )
)

schema_in = xo.schema({"year_months": "string"})
schema_out = xo.schema(
    {
        "Year": "int32",
        "Quarter": "int32",
        "Month": "int32",
        "DayofMonth": "int32",
        "DayOfWeek": "int32",
        "FlightDate": "date",
        "Reporting_Airline": "string",
        "DOT_ID_Reporting_Airline": "int64",
        "IATA_CODE_Reporting_Airline": "string",
        "Tail_Number": "string",
        "Flight_Number_Reporting_Airline": "int64",
        "OriginAirportID": "int64",
        "OriginAirportSeqID": "int64",
        "OriginCityMarketID": "int64",
        "Origin": "string",
        "OriginCityName": "string",
        "OriginState": "string",
        "OriginStateFips": "int32",
        "OriginStateName": "string",
        "OriginWac": "int32",
        "DestAirportID": "int64",
        "DestAirportSeqID": "int64",
        "DestCityMarketID": "int64",
        "Dest": "string",
        "DestCityName": "string",
        "DestState": "string",
        "DestStateFips": "int32",
        "DestStateName": "string",
        "DestWac": "int32",
        "CRSDepTime": "int32",
        "DepTime": "int32",
        "DepDelay": "float64",
        "DepDelayMinutes": "float64",
        "DepDel15": "float64",
        "DepartureDelayGroups": "int32",
        "DepTimeBlk": "string",
        "TaxiOut": "float64",
        "WheelsOff": "int32",
        "WheelsOn": "int32",
        "TaxiIn": "float64",
        "CRSArrTime": "int32",
        "ArrTime": "int32",
        "ArrDelay": "float64",
        "ArrDelayMinutes": "float64",
        "ArrDel15": "float64",
        "ArrivalDelayGroups": "int32",
        "ArrTimeBlk": "string",
        "Cancelled": "float64",
        "CancellationCode": "string",
        "Diverted": "float64",
        "CRSElapsedTime": "float64",
        "ActualElapsedTime": "float64",
        "AirTime": "float64",
        "Flights": "float64",
        "Distance": "float64",
        "DistanceGroup": "int32",
        "CarrierDelay": "float64",
        "WeatherDelay": "float64",
        "NASDelay": "float64",
        "SecurityDelay": "float64",
        "LateAircraftDelay": "float64",
        "FirstDepTime": "int32",
        "TotalAddGTime": "float64",
        "LongestAddGTime": "float64",
        "DivAirportLandings": "int32",
        "DivReachedDest": "float64",
        "DivActualElapsedTime": "float64",
        "DivArrDelay": "float64",
        "DivDistance": "float64",
        "Div1Airport": "string",
        "Div1AirportID": "int64",
        "Div1AirportSeqID": "int64",
        "Div1WheelsOn": "int32",
        "Div1TotalGTime": "float64",
        "Div1LongestGTime": "float64",
        "Div1WheelsOff": "int32",
        "Div1TailNum": "string",
        "Div2Airport": "string",
        "Div2AirportID": "int64",
        "Div2AirportSeqID": "int64",
        "Div2WheelsOn": "int32",
        "Div2TotalGTime": "float64",
        "Div2LongestGTime": "float64",
        "Div2WheelsOff": "int32",
        "Div2TailNum": "string",
        "Div3Airport": "string",
        "Div3AirportID": "int64",
        "Div3AirportSeqID": "int64",
        "Div3WheelsOn": "int32",
        "Div3TotalGTime": "float64",
        "Div3LongestGTime": "float64",
        "Div3WheelsOff": "int32",
        "Div3TailNum": "string",
        "Div4Airport": "string",
        "Div4AirportID": "int64",
        "Div4AirportSeqID": "int64",
        "Div4WheelsOn": "int32",
        "Div4TotalGTime": "float64",
        "Div4LongestGTime": "float64",
        "Div4WheelsOff": "int32",
        "Div4TailNum": "string",
        "Div5Airport": "string",
        "Div5AirportID": "int64",
        "Div5AirportSeqID": "int64",
        "Div5WheelsOn": "int32",
        "Div5TotalGTime": "float64",
        "Div5LongestGTime": "float64",
        "Div5WheelsOff": "int32",
        "Div5TailNum": "string",
        "_bts_year": "int32",
        "_bts_month": "int32",
        "_bts_source_file": "string",
        "_bts_source_url_prefix": "string",
    }
)

source_expr = flight_udxf(
    months_input,
    process_df=fetch_bts_months,
    maybe_schema_in=schema_in,
    maybe_schema_out=schema_out,
    con=con,
    make_udxf_kwargs={"name": "fetch_bts_months"},
)

cache = ParquetSnapshotCache.from_kwargs(source=con)
expr = source_expr.cache(cache)
