"""STEP 2: write one input packet per tag id to followup/autotag/inputs/<id>.json. No model calls.

A packet holds only: table name, column or metric name (plus the filter value for long-table
metrics), DuckDB dtype, 10 sample rows, null count, distinct count, min/max, distinct values if
<= 20, and vendor-side documentation (PREREG design decisions 3-6):
  - SEC tables: url and retrieved_on per company from data/raw/sec/retrieved.json
  - pageviews:  title, url and retrieved_at_utc per article from data/raw/wiki/retrieved.json
  - comps:      definition_text and source_url per definition from comps_definitions
                (the notes column is excluded everywhere)
  - macro:      the vendor header rows inside data/raw/macro/*.xlsx

The tag ids, tables and filters are read from tags/tags.yaml (they are copied into every draft and
not scored); nothing else from tags.yaml is read. The database is opened read-only.

Run: python followup/autotag/build_inputs.py
"""
import json
import random
import sys
import warnings
from pathlib import Path

import duckdb
import openpyxl
import yaml

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
INPUTS = HERE / "inputs"
DB_PATH = ROOT / "data" / "warehouse.duckdb"
TAGS_PATH = ROOT / "tags" / "tags.yaml"
RAW = ROOT / "data" / "raw"

SAMPLE_ROWS = 10
SAMPLE_SEED = 20261029
MAX_DISTINCT_LISTED = 20
EXCLUDED_COLUMNS = {"comps_definitions": {"notes"}}
WITHHELD_VALUES = {("comps_definitions", "notes")}  # stats only, no values (PREREG decision 5)

# The Census file has no series id inside it; this is the id the warehouse stores for it.
MACRO_FILES = {"CUSR0000SEFV": RAW / "macro" / "bls_CUSR0000SEFV.xlsx",
               "CENSUS_722_SA": RAW / "macro" / "census_naics722_sa.xlsx"}


def structural_keys():
    """(id, table, filter) for every tag; the only fields read from tags.yaml."""
    raw = yaml.safe_load(TAGS_PATH.read_text())
    return [(e["id"], e["table"], e.get("filter")) for e in raw]


def _jsonable(v):
    return v if v is None or isinstance(v, (str, int, float, bool)) else str(v)


def _macro_header(path):
    """Vendor header rows above the data in a macro workbook, as text lines."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ws = openpyxl.load_workbook(path).worksheets[0]
    lines = []
    for row in ws.iter_rows(values_only=True):
        cells = [str(c) for c in row if c is not None]
        if not cells:
            continue
        if cells[0] in ("Year", "Period"):  # the data table starts here
            break
        lines.append(" ".join(cells))
    return lines


def vendor_docs(con, table, flt):
    if table == "fundamentals":
        sec = json.loads((RAW / "sec" / "retrieved.json").read_text())
        return {"sec_companyfacts": {t: {"url": v["url"], "retrieved_on": v["retrieved_on"]}
                                     for t, v in sec.items()}}
    if table == "brand_attention_daily":
        wiki = json.loads((RAW / "wiki" / "retrieved.json").read_text())
        return {"wikimedia_pageviews": [{"title": v["title"], "url": v["url"],
                                         "retrieved_at_utc": v["retrieved_at_utc"]}
                                        for v in wiki.values()]}
    if table in ("comps_quarterly", "comps_definitions"):
        rows = con.execute("SELECT definition_id, ticker, definition_text, source_url "
                           "FROM comps_definitions ORDER BY ticker").fetchall()
        return {"company_metric_definitions": [
            {"definition_id": d, "ticker": t, "definition_text": txt, "source_url": u}
            for d, t, txt, u in rows]}
    if table == "macro_monthly":
        ids = [flt["series_id"]] if flt and "series_id" in flt else sorted(MACRO_FILES)
        return {"source_file_headers": {s: _macro_header(MACRO_FILES[s]) for s in ids}}
    raise ValueError(f"no vendor documentation rule for table {table}")


def _where(flt):
    if not flt:
        return "", []
    parts, params = [], []
    for col, val in flt.items():
        if isinstance(val, list):
            parts.append(f"{col} IN ({','.join('?' * len(val))})")
            params += val
        else:
            parts.append(f"{col} = ?")
            params.append(val)
    return " WHERE " + " AND ".join(parts), params


def packet(con, tag_id, table, flt):
    if tag_id.startswith("derived."):
        # PREREG decision 3: the id and the list filter, nothing else.
        return {"id": tag_id, "table": table, "filter": flt}

    dtypes = {c: t for c, t, *_ in con.execute(f"DESCRIBE {table}").fetchall()}
    col_names = [c for c in dtypes if c not in EXCLUDED_COLUMNS.get(table, set())]
    where, params = _where(flt)
    # A long-table metric is the 'value' column under its filter; otherwise the id names the column.
    column = "value" if flt else tag_id.split(".", 1)[1]
    dtype = dtypes[column]

    all_rows = con.execute(f"SELECT {', '.join(col_names)} FROM {table}{where} "
                           f"ORDER BY ALL", params).fetchall()
    rng = random.Random(f"{SAMPLE_SEED}:{tag_id}")
    sample = rng.sample(all_rows, min(SAMPLE_ROWS, len(all_rows)))
    sample_rows = [{c: _jsonable(v) for c, v in zip(col_names, r)} for r in sample]

    n, nulls, distinct, lo, hi = con.execute(
        f"SELECT count(*), count(*) - count({column}), count(DISTINCT {column}), "
        f"min({column}), max({column}) FROM {table}{where}", params).fetchone()
    out = {"table": table, "column": column}
    if flt:
        out["filter"] = flt
    out.update({"duckdb_dtype": dtype, "row_count": n, "null_count": nulls,
                "distinct_count": distinct})
    if (table, column) in WITHHELD_VALUES:
        out["values_withheld"] = True
    else:
        out["sample_rows"] = sample_rows
        out["min"], out["max"] = _jsonable(lo), _jsonable(hi)
        if distinct <= MAX_DISTINCT_LISTED:
            out["distinct_values"] = [_jsonable(r[0]) for r in con.execute(
                f"SELECT DISTINCT {column} FROM {table}{where} ORDER BY 1", params).fetchall()]
    out["vendor_documentation"] = vendor_docs(con, table, flt)
    return out


def main():
    INPUTS.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        keys = structural_keys()
        for tag_id, table, flt in keys:
            p = packet(con, tag_id, table, flt)
            (INPUTS / f"{tag_id}.json").write_text(json.dumps(p, indent=1) + "\n")
    finally:
        con.close()
    print(f"wrote {len(keys)} packets to {INPUTS.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.exit(main())
