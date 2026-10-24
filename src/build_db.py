"""Phase 5: build the DuckDB warehouse (SPEC.md §7).

Reads the three parquet files in data/interim/ and the two comps CSVs in data/, creates
data/warehouse.duckdb (replacing any existing file) with exactly the five tables in SPEC §7, loads
them as filed (no cleaning, filling, rounding or dropping; YTD rows and parent rows included),
then runs the data checks D1-D9. If an input column does not match §7, it stops without building.

Run: python src/build_db.py
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"
INTERIM = ROOT / "data" / "interim"

# SPEC §7, verbatim apart from the comments.
DDL = """
CREATE TABLE fundamentals (
  ticker VARCHAR, cik VARCHAR, metric VARCHAR, concept VARCHAR,
  value DOUBLE, unit VARCHAR,
  period_start DATE,
  period_end DATE,
  period_basis VARCHAR,
  fiscal_year INTEGER, fiscal_quarter INTEGER,
  form VARCHAR, accession VARCHAR, filed DATE
);
CREATE TABLE comps_quarterly (
  ticker VARCHAR, fiscal_year INTEGER, fiscal_quarter INTEGER,
  comp_sales_pct DOUBLE, definition_id VARCHAR, source_url VARCHAR
);
CREATE TABLE comps_definitions (
  definition_id VARCHAR, ticker VARCHAR, definition_text VARCHAR,
  source_url VARCHAR, notes VARCHAR
);
CREATE TABLE brand_attention_daily (
  date DATE, article_title VARCHAR, brand VARCHAR,
  grain VARCHAR,
  parent_ticker VARCHAR, views BIGINT
);
CREATE TABLE macro_monthly (
  series_id VARCHAR, date DATE, value DOUBLE, retrieved_on DATE
);
"""

# table -> (source path, expected columns in SPEC §7 order)
SOURCES = {
    "fundamentals": (INTERIM / "fundamentals.parquet", [
        "ticker", "cik", "metric", "concept", "value", "unit", "period_start", "period_end",
        "period_basis", "fiscal_year", "fiscal_quarter", "form", "accession", "filed"]),
    "comps_quarterly": (ROOT / "data" / "comps_quarterly.csv", [
        "ticker", "fiscal_year", "fiscal_quarter", "comp_sales_pct", "definition_id", "source_url"]),
    "comps_definitions": (ROOT / "data" / "comps_definitions.csv", [
        "definition_id", "ticker", "definition_text", "source_url", "notes"]),
    "brand_attention_daily": (INTERIM / "brand_attention_daily.parquet", [
        "date", "article_title", "brand", "grain", "parent_ticker", "views"]),
    "macro_monthly": (INTERIM / "macro_monthly.parquet", [
        "series_id", "date", "value", "retrieved_on"]),
}

TICKERS = ["CMG", "WING", "YUM", "DRI"]
EXPECTED_BRANDS = 10


def read_source(table):
    path, _ = SOURCES[table]
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    # Read CSV cells as text so nothing is parsed, rounded or turned into NULL on the way; DuckDB
    # casts them to the §7 types and raises on anything that does not convert.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def load_frames():
    frames, bad = {}, []
    for table, (path, expected) in SOURCES.items():
        df = read_source(table)
        if list(df.columns) != expected:
            bad.append((table, path, expected, list(df.columns)))
        frames[table] = df
    if bad:
        print("COLUMN MISMATCH against SPEC §7 (nothing was built):")
        for table, path, expected, actual in bad:
            print(f"  {table} ({path.relative_to(ROOT)})")
            print(f"    SPEC §7 : {expected}")
            print(f"    in file : {actual}")
            print(f"    missing : {[c for c in expected if c not in actual]}")
            print(f"    extra   : {[c for c in actual if c not in expected]}")
        sys.exit(1)
    return frames


def build(frames):
    DB_PATH.unlink(missing_ok=True)
    DB_PATH.with_name(DB_PATH.name + ".wal").unlink(missing_ok=True)
    con = duckdb.connect(str(DB_PATH))
    con.execute(DDL)
    for table, (_, cols) in SOURCES.items():
        df = frames[table]  # noqa: F841 (referenced by DuckDB's replacement scan)
        col_list = ", ".join(cols)
        con.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM df")
    con.close()


class Checks:
    def __init__(self):
        self.results = {}

    def section(self, key, title):
        print(f"\n=== {key}. {title} ===")

    def verdict(self, key, ok, msg):
        self.results[key] = ok
        print(f"{key} {'PASS' if ok else 'FAIL'}: {msg}")


def show(con, sql):
    df = con.execute(sql).df()
    print(df.to_string(index=False) if len(df) else "(no rows)")
    return df


def run_checks(con):
    c = Checks()

    c.section("D1", "Row counts per table")
    counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in SOURCES}
    for t, n in counts.items():
        print(f"{t}: {n}")
    src_counts = {t: len(read_source(t)) for t in SOURCES}
    c.verdict("D1", counts == src_counts, "every table's row count equals its source file's row count")

    c.section("D2", "Distinct fiscal quarters with a total_assets value, per company (must be 8)")
    df = show(con, """
        SELECT ticker, count(DISTINCT (fiscal_year, fiscal_quarter)) AS fiscal_quarters
        FROM fundamentals WHERE metric = 'total_assets' AND value IS NOT NULL
        GROUP BY ticker ORDER BY ticker""")
    got = dict(zip(df.ticker, df.fiscal_quarters))
    c.verdict("D2", all(got.get(t) == 8 for t in TICKERS) and set(got) == set(TICKERS),
              "each of CMG, WING, YUM, DRI has 8")

    c.section("D3", "Distinct dates per brand/parent, views summed across titles (must be 731)")
    df = show(con, """
        SELECT brand, grain, count(*) AS dates FROM (
          SELECT brand, grain, date, sum(views) AS views FROM brand_attention_daily
          GROUP BY brand, grain, date)
        GROUP BY brand, grain ORDER BY grain, brand""")
    c.verdict("D3", len(df) == EXPECTED_BRANDS and (df.dates == 731).all(),
              f"{len(df)} brands/parents, each with 731 dates")

    c.section("D4", "Duplicate keys (must be none)")
    dup_sql = {
        "fundamentals duration (ticker, metric, period_start, period_end)": """
            SELECT ticker, metric, period_start, period_end, count(*) AS n FROM fundamentals
            WHERE period_start IS NOT NULL GROUP BY ALL HAVING count(*) > 1""",
        "fundamentals instant (ticker, metric, period_end)": """
            SELECT ticker, metric, period_end, count(*) AS n FROM fundamentals
            WHERE period_start IS NULL GROUP BY ALL HAVING count(*) > 1""",
        "brand_attention_daily (date, article_title)": """
            SELECT date, article_title, count(*) AS n FROM brand_attention_daily
            GROUP BY ALL HAVING count(*) > 1""",
        "macro_monthly (series_id, date)": """
            SELECT series_id, date, count(*) AS n FROM macro_monthly
            GROUP BY ALL HAVING count(*) > 1""",
        "comps_quarterly (ticker, fiscal_year, fiscal_quarter)": """
            SELECT ticker, fiscal_year, fiscal_quarter, count(*) AS n FROM comps_quarterly
            GROUP BY ALL HAVING count(*) > 1""",
    }
    all_clean = True
    for name, sql in dup_sql.items():
        print(f"{name}:")
        dups = show(con, sql)
        all_clean &= dups.empty
    c.verdict("D4", all_clean, "no duplicate keys in any table")

    c.section("D5", "Rows with period_basis = 'other' (must be 0)")
    n = con.execute("SELECT count(*) FROM fundamentals WHERE period_basis = 'other'").fetchone()[0]
    print(f"rows: {n}")
    c.verdict("D5", n == 0, "no 'other' rows")

    c.section("D6", "comps_quarterly (12 rows) and comps_definitions (3 rows), no nulls")
    ok = True
    for t, want in (("comps_quarterly", 12), ("comps_definitions", 3)):
        cols = [r[0] for r in con.execute(f"DESCRIBE {t}").fetchall()]
        nulls = con.execute(
            f"SELECT {', '.join(f'count(*) FILTER (WHERE {col} IS NULL)' for col in cols)} FROM {t}"
        ).fetchone()
        n = counts[t]
        print(f"{t}: {n} rows; nulls per column: {dict(zip(cols, nulls))}")
        ok &= n == want and sum(nulls) == 0
    c.verdict("D6", ok, "12 comps rows, 3 definitions, no nulls")

    c.section("D7", "macro_monthly: rows and missing months per series (32 rows each; CPI 2025-10 the only gap)")
    df = show(con, """
        SELECT series_id, count(*) AS n, min(date) AS first_month, max(date) AS last_month
        FROM macro_monthly GROUP BY series_id ORDER BY series_id""")
    missing = {}
    for s in df.series_id:
        missing[s] = [r[0].isoformat() for r in con.execute("""
            SELECT m::DATE FROM (
              SELECT unnest(generate_series(min(date), max(date), INTERVAL 1 MONTH)) AS m
              FROM macro_monthly WHERE series_id = ?)
            WHERE m::DATE NOT IN (SELECT date FROM macro_monthly WHERE series_id = ?)
            ORDER BY 1""", [s, s]).fetchall()]
        print(f"{s}: missing months between first and last: {missing[s] or 'none'}")
    c.verdict("D7", set(df.series_id) == {"CUSR0000SEFV", "CENSUS_722_SA"} and (df.n == 32).all()
              and missing == {"CUSR0000SEFV": ["2025-10-01"], "CENSUS_722_SA": []},
              "32 rows per series; the only missing month is CPI 2025-10")

    c.section("D8", "Concept chosen per (ticker, metric), with fiscal-period coverage (must be 8/8)")
    df = show(con, """
        SELECT ticker, metric, concept,
               count(DISTINCT (fiscal_year, fiscal_quarter)) AS periods_covered, 8 AS periods_needed
        FROM fundamentals GROUP BY ticker, metric, concept ORDER BY ticker, metric""")
    one_concept = df.groupby(["ticker", "metric"]).size().eq(1).all()
    c.verdict("D8", len(df) == len(TICKERS) * 7 and one_concept and (df.periods_covered == 8).all(),
              "28 (ticker, metric) pairs, one concept each, 8/8 periods; compare with the Phase 1 "
              "coverage table by eye")

    c.section("D9", "Read-only test: INSERT on a read_only connection must fail")
    ro = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        ro.execute("INSERT INTO macro_monthly VALUES ('TEST', DATE '2000-01-01', 0, DATE '2000-01-01')")
        c.verdict("D9", False, "INSERT succeeded on a read-only connection")
    except duckdb.Error as e:
        print(f"{type(e).__name__}: {e}")
        c.verdict("D9", True, "INSERT was rejected")
    finally:
        ro.close()

    return c.results


def main():
    frames = load_frames()
    build(frames)
    print(f"Built {DB_PATH.relative_to(ROOT)}")
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        results = run_checks(con)
    finally:
        con.close()
    print("\n=== Summary ===")
    for k, ok in results.items():
        print(f"{k}: {'PASS' if ok else 'FAIL'}")
    if not all(results.values()):
        sys.exit("One or more checks failed. Stopping.")


if __name__ == "__main__":
    main()
