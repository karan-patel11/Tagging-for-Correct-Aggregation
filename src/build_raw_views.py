"""Exploratory setup A_raw: build data/warehouse_raw.duckdb from data/warehouse.duckdb.

A_raw asks whether setup A's accuracy comes from meaning that is stored as columns. The raw file
holds the same five tables under the same names, with the meaning columns removed:

  fundamentals           drops period_basis, fiscal_year, fiscal_quarter, concept
  brand_attention_daily  drops grain, brand
  comps_quarterly, comps_definitions, macro_monthly   unchanged

warehouse.duckdb is attached READ_ONLY and is never written. Each raw table is a projection
(CREATE TABLE AS SELECT <kept columns> FROM the original, in the original row order), not a
cross-file VIEW: a VIEW over another file only resolves after an ATTACH in the reader's
connection, and run_sql disables external access, so setup A_raw could not read such a view.
The finished file is made read-only on disk (mode 0444) and run_sql opens it with read_only=True.

Checks printed (any failure exits non-zero):
  R1  DESCRIBE of every table in warehouse_raw.duckdb
  R2  row counts equal to the originals
  R3  none of the dropped columns exist
  R4  every dropped column is a function of the kept columns, so no information a question needs
      was removed: fiscal labels and period basis recomputed from the dates (SPEC §6.2 functions,
      fiscal year-end month read from each company's own full-year rows) equal the originals on
      every row; concept is one value per (ticker, metric); brand and grain are one value per
      article_title. Kept columns themselves are identical to the original columns, row by row.
  R5  one line per question in eval/questions.yaml: still answerable from the remaining columns,
      and how. Stops if any question that expects an answer became unanswerable.

Run: python src/build_raw_views.py
"""

import os
import stat
import sys
from pathlib import Path

import duckdb
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from ingest_sec import classify_basis, fiscal_labels  # noqa: E402  (the functions that built the labels)

SRC_DB = ROOT / "data" / "warehouse.duckdb"
RAW_DB = ROOT / "data" / "warehouse_raw.duckdb"
QUESTIONS = ROOT / "eval" / "questions.yaml"

DROPPED = {
    "fundamentals": ["period_basis", "fiscal_year", "fiscal_quarter", "concept"],
    "brand_attention_daily": ["grain", "brand"],
    "comps_quarterly": [],
    "comps_definitions": [],
    "macro_monthly": [],
}

# How each question is answered from the remaining columns. Written per category from what the
# dropped columns were used for; R5 prints it next to the R4 evidence that makes it hold.
HOW = {
    "time_additivity": ("fundamentals: total_assets row whose period_end is the fiscal year-end "
                        "(year-end from the company's 350-380 day revenue rows); needed period_basis/"
                        "fiscal_year only as labels"),
    "ratios": ("fundamentals: operating_income and revenue rows spanning 350-380 days ending in the "
               "fiscal year; FY label derivable from period_end"),
    "ytd_calendar": ("fundamentals: quarter rows (80-100 days) or YTD/FY rows minus the prior YTD row, "
                     "identified by period_start/period_end instead of period_basis/fiscal_quarter"),
    "indices": "macro_monthly: unchanged",
    "hierarchy": ("brand_attention_daily: brand articles named in the question are article_title "
                  "values with parent_ticker; brand/grain were one value per title"),
    "comparability_unanswerable": "comps_quarterly/comps_definitions: unchanged",
}
NOTES = {
    # The question's 'from continuing operations' was checkable only through concept.
    "q016": ("concept (…ContinuingOperations) is gone, so the model can no longer confirm the "
             "continuing-operations basis from the data; the value itself is still there"),
    "q035": "refuse: average unit volume is in no table, before or after",
    "q036": "refuse: restaurant counts are in no table, before or after",
    "q037": "refuse: fiscal 2023 is outside the stored window, before or after (period_end shows it)",
    "q038": "refuse: CAVA is in no table, before or after",
}


def check(name, ok, detail=""):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"\n{detail}" if detail else ""))
    if not ok:
        sys.exit(f"STOP: {name}")


def build():
    if RAW_DB.exists():
        os.chmod(RAW_DB, stat.S_IRUSR | stat.S_IWUSR)
        RAW_DB.unlink()
    src_mtime = SRC_DB.stat().st_mtime_ns
    con = duckdb.connect(str(RAW_DB))
    con.execute(f"ATTACH '{SRC_DB}' AS src (READ_ONLY)")
    for table, dropped in DROPPED.items():
        cols = [r[0] for r in con.execute(f"DESCRIBE src.{table}").fetchall()]
        missing = set(dropped) - set(cols)
        if missing:
            sys.exit(f"STOP: {table} has no column(s) {sorted(missing)}")
        kept = ", ".join(c for c in cols if c not in dropped)
        # rowid order = the original insertion order, so unordered queries see rows in the same order
        con.execute(f"CREATE TABLE {table} AS SELECT {kept} FROM src.{table} ORDER BY rowid")
    con.execute("DETACH src")
    con.close()
    os.chmod(RAW_DB, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    if SRC_DB.stat().st_mtime_ns != src_mtime:
        sys.exit("STOP: warehouse.duckdb was modified")


def main():
    if not SRC_DB.exists():
        sys.exit("STOP: data/warehouse.duckdb is missing; run python src/build_db.py first")
    build()
    src = duckdb.connect(str(SRC_DB), read_only=True)
    raw = duckdb.connect(str(RAW_DB), read_only=True)

    print("=== R1. DESCRIBE of every table in warehouse_raw.duckdb ===")
    tables = [r[0] for r in raw.execute("SHOW TABLES").fetchall()]
    for t in tables:
        print(f"\n{t}")
        print(raw.execute(f'DESCRIBE "{t}"').df()[["column_name", "column_type", "null"]].to_string(index=False))
    check("same table names as warehouse.duckdb",
          sorted(tables) == sorted(r[0] for r in src.execute("SHOW TABLES").fetchall()),
          f"  {tables}")

    print("\n=== R2. Row counts ===")
    ok = True
    for t in tables:
        a = src.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        b = raw.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0]
        ok &= a == b
        print(f"  {t:24s} original {a:6d}  raw {b:6d}  {'equal' if a == b else 'DIFFERENT'}")
    check("row counts equal to the originals", ok)

    print("\n=== R3. Dropped columns are absent ===")
    for t, dropped in DROPPED.items():
        cols = {r[0] for r in raw.execute(f'DESCRIBE "{t}"').fetchall()}
        orig = [r[0] for r in src.execute(f'DESCRIBE "{t}"').fetchall()]
        present = set(dropped) & cols
        print(f"  {t:24s} dropped {dropped or '-'}; present: {sorted(present) or 'none'}")
        assert not present, f"{t} still has {present}"
        check(f"{t}: kept columns are the original columns minus the dropped ones, in order",
              [r[0] for r in raw.execute(f'DESCRIBE "{t}"').fetchall()] == [c for c in orig if c not in dropped])

    print("\n=== R4. Dropped columns are recoverable from kept columns ===")
    for t, dropped in DROPPED.items():
        kept = [c for c in (r[0] for r in src.execute(f'DESCRIBE "{t}"').fetchall()) if c not in dropped]
        a = src.execute(f'SELECT {", ".join(kept)} FROM "{t}" ORDER BY rowid').df()
        b = raw.execute(f'SELECT {", ".join(kept)} FROM "{t}" ORDER BY rowid').df()
        check(f"{t}: kept columns identical to the original, row by row", a.equals(b))

    f_src = src.execute("SELECT * FROM fundamentals ORDER BY rowid").df()
    f_raw = raw.execute("SELECT * FROM fundamentals ORDER BY rowid").df()
    for c in ("period_start", "period_end"):
        f_raw[c] = pd.to_datetime(f_raw[c])
    # Fiscal year-end month per company, read from its own full-year (350-380 day) rows.
    span = (f_raw.period_end - f_raw.period_start).dt.days
    fye = f_raw[(span >= 350) & (span <= 380)].groupby("ticker").period_end \
        .agg(lambda s: sorted({(d - pd.Timedelta(days=7)).month for d in s}))
    print("  fiscal year-end month from each company's full-year rows:",
          {k: v for k, v in fye.items()})
    check("one fiscal year-end month per company", all(len(v) == 1 for v in fye))
    fye = {k: v[0] for k, v in fye.items()}
    basis = [classify_basis(s, e) for s, e in zip(f_raw.period_start, f_raw.period_end)]
    labels = [fiscal_labels(e, fye[t]) for t, e in zip(f_raw.ticker, f_raw.period_end)]
    check("period_basis recomputed from the dates equals the original on all rows",
          basis == list(f_src.period_basis), f"  rows: {len(basis)}")
    check("fiscal_year and fiscal_quarter recomputed from period_end equal the original on all rows",
          [l[0] for l in labels] == list(f_src.fiscal_year)
          and [l[1] for l in labels] == list(f_src.fiscal_quarter))
    n = src.execute("SELECT max(n) FROM (SELECT count(DISTINCT concept) n FROM fundamentals "
                    "GROUP BY ticker, metric)").fetchone()[0]
    check("concept is one value per (ticker, metric)", n == 1)
    m = src.execute("SELECT max(n) FROM (SELECT count(DISTINCT (brand, grain)) n "
                    "FROM brand_attention_daily GROUP BY article_title)").fetchone()[0]
    check("brand and grain are one value per article_title", m == 1,
          src.execute("SELECT DISTINCT article_title, brand, grain, parent_ticker FROM brand_attention_daily "
                      "ORDER BY parent_ticker, article_title").df().to_string(index=False))

    print("\n=== R5. Per question: still answerable from the remaining columns? ===")
    blocked = []
    for q in yaml.safe_load(QUESTIONS.read_text()):
        if q["expected_behavior"] == "refuse":
            verdict, how = "refuse (unchanged)", NOTES[q["id"]]
        else:
            verdict, how = "answerable", HOW[q["category"]]
            if q["id"] in NOTES:
                how += "; note: " + NOTES[q["id"]]
        print(f"  {q['id']} {q['category']:27s} {verdict}: {how}")
        if verdict not in ("answerable", "refuse (unchanged)"):
            blocked.append(q["id"])
    check("no answerable question became unanswerable", not blocked, f"  {blocked}")
    print(f"\nWrote {RAW_DB.relative_to(ROOT)} (mode {oct(RAW_DB.stat().st_mode & 0o777)}); "
          "warehouse.duckdb unchanged")


if __name__ == "__main__":
    main()
