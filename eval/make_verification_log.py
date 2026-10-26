"""Phase 10 prep: write eval/verification_log.csv (SPEC.md §11.3), one row per number to look up.

Reads eval/questions.yaml and only the metadata columns of data/warehouse.duckdb (accession, form,
cik, dates), opened read_only. It never reads a value column and never writes an answer-key or
computed value. value_seen is pre-filled only for numbers recorded in tests/expected_values.md.
Existing value_seen entries are kept (matched by question_id + piece tag) when the file is rebuilt.

Every where_in_source starts with a piece tag in brackets that eval/check_verification.py parses:
  [sec:TICKER:metric:BASIS:FYyyyy]  [comps:TICKER:FY2025Qn]  [cpi:YYYY-MM]  [census722:YYYY-MM]
  [views:Article_Title:CYyyyyQn]  [absent:what]

Run: python eval/make_verification_log.py
"""

import csv
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"
QUESTIONS = ROOT / "eval" / "questions.yaml"
OUT = ROOT / "eval" / "verification_log.csv"
COLUMNS = ["question_id", "source_url", "where_in_source", "value_seen", "matches", "notes"]

con = duckdb.connect(str(DB_PATH), read_only=True)

# Questions written to replace the 4 dropped ones go first. Add their exact text here, and their
# pieces to PIECES, once they are in questions.yaml.
REPLACEMENTS = []

# ---------------------------------------------------------------------------------------------
# Pieces per question, keyed by exact question text (ids shift when questions are added).
# ---------------------------------------------------------------------------------------------

def sec(t, m, fy, *bases):
    return [("sec", t, m, fy, b) for b in bases]


def margin(*pairs):
    out = []
    for t, fy in pairs:
        out += sec(t, "operating_income", fy, "FY") + sec(t, "revenue", fy, "FY")
    return out


YUM_ARTICLES = ["KFC", "Taco_Bell", "Pizza_Hut", "Habit_Burger_&_Grill", "The_Habit_Burger_Grill"]
DRI_ARTICLES = ["Olive_Garden", "LongHorn_Steakhouse"]


def views(articles, *quarters):
    return [("views", a, q) for q in quarters for a in articles]


def cpi(*ms):
    return [("cpi", m) for m in ms]


def census(*ms):
    return [("census722", m) for m in ms]


def comps(fq):
    return [("comps", "CMG", 2025, fq), ("comps", "WING", 2025, fq)]


PIECES = {
    "What were Chipotle's total assets at the end of fiscal 2025, in US dollars?":
        sec("CMG", "total_assets", 2025, "instant"),
    "What were Wingstop's total assets at the end of fiscal 2025 (year ended December 27, 2025), in US dollars?":
        sec("WING", "total_assets", 2025, "instant"),
    "What were Yum! Brands' total assets at the end of fiscal 2025, in US dollars?":
        sec("YUM", "total_assets", 2025, "instant"),
    "What were Darden's total assets at the end of fiscal 2025 (year ended May 25, 2025), in US dollars?":
        sec("DRI", "total_assets", 2025, "instant"),
    "What were Yum! Brands' total assets at the end of fiscal 2024, in US dollars?":
        sec("YUM", "total_assets", 2024, "instant"),
    "What were Wingstop's total assets at the end of fiscal 2024 (year ended December 28, 2024), in US dollars?":
        sec("WING", "total_assets", 2024, "instant"),
    "What was the combined fiscal 2025 operating margin of Chipotle and Wingstop, calculated as their total operating income divided by their total revenue, in percent?":
        margin(("CMG", 2025), ("WING", 2025)),
    "What was the combined fiscal 2025 operating margin of Chipotle and Yum! Brands, calculated as their total operating income divided by their total revenue, in percent?":
        margin(("CMG", 2025), ("YUM", 2025)),
    "What was the combined fiscal 2025 operating margin of Chipotle, Wingstop and Yum! Brands, calculated as their total operating income divided by their total revenue, in percent?":
        margin(("CMG", 2025), ("WING", 2025), ("YUM", 2025)),
    "What was the combined operating margin of Chipotle (fiscal 2025), Yum! Brands (fiscal 2025) and Darden (fiscal 2025, year ended May 25, 2025), calculated as their total operating income divided by their total revenue, in percent?":
        margin(("CMG", 2025), ("YUM", 2025), ("DRI", 2025)),
    "What was the combined fiscal 2025 operating margin of Wingstop and Yum! Brands, calculated as their total operating income divided by their total revenue, in percent?":
        margin(("WING", 2025), ("YUM", 2025)),
    "What was Chipotle's net cash from operating activities in fiscal Q2 2025 (the three months ended June 30, 2025), in US dollars?":
        sec("CMG", "op_cash_flow", 2025, "YTD6", "Q"),
    "What was Yum! Brands' net cash from operating activities in fiscal Q3 2025 (the three months ended September 30, 2025), in US dollars?":
        sec("YUM", "op_cash_flow", 2025, "YTD9", "YTD6"),
    "What was Chipotle's capital expenditure in fiscal Q4 2025, in US dollars?":
        sec("CMG", "capex", 2025, "FY", "YTD9"),
    "What was Wingstop's capital expenditure in fiscal Q4 2025 (quarter ended December 27, 2025), in US dollars?":
        sec("WING", "capex", 2025, "FY", "YTD9"),
    "What was Darden's net cash from operating activities from continuing operations in fiscal Q3 2025 (quarter ended February 23, 2025), in US dollars?":
        sec("DRI", "op_cash_flow", 2025, "YTD9", "YTD6"),
    "What was Darden's total revenue in fiscal Q4 2026 (the 14-week quarter ended May 31, 2026), in US dollars?":
        sec("DRI", "revenue", 2026, "FY", "YTD9"),
    "What was the percent change in the CPI for food away from home (seasonally adjusted) from December 2024 to December 2025?":
        cpi("2024-12", "2025-12"),
    "What was the percent change in the CPI for food away from home (seasonally adjusted) from June 2024 to June 2025?":
        cpi("2024-06", "2025-06"),
    "What was the annual average of the monthly CPI for food away from home (seasonally adjusted) for calendar 2024, in index points?":
        cpi(*[f"2024-{m:02d}" for m in range(1, 13)]),
    "What was the percent change in the CPI for food away from home (seasonally adjusted) from December 2024 to June 2025?":
        cpi("2024-12", "2025-06"),
    "What were total US food services and drinking places sales (seasonally adjusted) for calendar Q3 2024, in millions of US dollars?":
        census("2024-07", "2024-08", "2024-09"),
    "What were total US food services and drinking places sales (seasonally adjusted) for calendar Q1 2025, in millions of US dollars?":
        census("2025-01", "2025-02", "2025-03"),
    "What were total US food services and drinking places sales (seasonally adjusted) for calendar Q2 2025, in millions of US dollars?":
        census("2025-04", "2025-05", "2025-06"),
    "How many English Wikipedia views did Yum! Brands' four brand articles (KFC, Taco Bell, Pizza Hut, and Habit Burger Grill under both its current and former titles) receive combined in calendar Q4 2024?":
        views(YUM_ARTICLES, "CY2024Q4"),
    "How many English Wikipedia views did Yum! Brands' four brand articles (KFC, Taco Bell, Pizza Hut, and Habit Burger Grill under both its current and former titles) receive combined in calendar Q1 2025?":
        views(YUM_ARTICLES, "CY2025Q1"),
    "How many English Wikipedia views did Yum! Brands' four brand articles (KFC, Taco Bell, Pizza Hut, and Habit Burger Grill under both its current and former titles) receive combined in calendar Q2 2025?":
        views(YUM_ARTICLES, "CY2025Q2"),
    "How many English Wikipedia views did Darden's two brand articles, Olive Garden and LongHorn Steakhouse, receive combined in calendar Q2 2024?":
        views(DRI_ARTICLES, "CY2024Q2"),
    "How many English Wikipedia views did Darden's two brand articles, Olive Garden and LongHorn Steakhouse, receive combined in calendar Q3 2025?":
        views(DRI_ARTICLES, "CY2025Q3"),
    "What share of the combined English Wikipedia views of Yum! Brands' four brand articles (KFC, Taco Bell, Pizza Hut, and Habit Burger Grill under both its current and former titles) went to KFC in calendar 2025, in percent?":
        views(YUM_ARTICLES, "CY2025Q1", "CY2025Q2", "CY2025Q3", "CY2025Q4"),
    "What share of the combined English Wikipedia views of Yum! Brands' four brand articles (KFC, Taco Bell, Pizza Hut, and Habit Burger Grill under both its current and former titles) went to KFC in calendar Q4 2024, in percent?":
        views(YUM_ARTICLES, "CY2024Q4"),
    "By how many percentage points did Chipotle's comparable sales growth exceed Wingstop's in fiscal Q1 2025?":
        comps(1),
    "By how many percentage points did Chipotle's comparable sales growth exceed Wingstop's in fiscal Q2 2025?":
        comps(2),
    "By how many percentage points did Chipotle's comparable sales growth exceed Wingstop's in fiscal Q4 2025?":
        comps(4),
}

SEVEN_METRICS = "('revenue','operating_income','net_income','op_cash_flow','capex','total_assets','diluted_eps')"
ABSENT = {
    "What was Chipotle's average unit volume in fiscal 2025, in US dollars?": (
        "average unit volume (AUV)",
        "No AUV metric in fundamentals and no AUV-like column in any table.",
        f"SELECT (SELECT count(*) FROM fundamentals WHERE metric NOT IN {SEVEN_METRICS}) + "
        "(SELECT count(*) FROM information_schema.columns WHERE column_name ILIKE '%auv%' "
        "OR column_name ILIKE '%unit_volume%')"),
    "How many Wingstop restaurants were open at the end of fiscal 2025 (year ended December 27, 2025)?": (
        "restaurant count",
        "No restaurant-count metric in fundamentals and no count-of-units column in any table.",
        f"SELECT (SELECT count(*) FROM fundamentals WHERE metric NOT IN {SEVEN_METRICS}) + "
        "(SELECT count(*) FROM information_schema.columns WHERE column_name ILIKE '%restaurant%' "
        "OR column_name ILIKE '%store%' OR column_name ILIKE '%unit_count%')"),
    "What was Chipotle's total revenue in fiscal 2023, in US dollars?": (
        "CMG fiscal 2023",
        "No CMG fundamentals row for fiscal 2023 or ending before 2024-01-01 (window is FY2024-FY2025).",
        "SELECT count(*) FROM fundamentals WHERE ticker='CMG' AND (fiscal_year=2023 "
        "OR period_end < DATE '2024-01-01')"),
    "What was CAVA's comparable restaurant sales growth in fiscal Q2 2025, in percent?": (
        "CAVA",
        "CAVA is in no table: comps, definitions, fundamentals, pageviews.",
        "SELECT (SELECT count(*) FROM comps_quarterly WHERE ticker='CAVA') + "
        "(SELECT count(*) FROM comps_definitions WHERE ticker='CAVA') + "
        "(SELECT count(*) FROM fundamentals WHERE ticker='CAVA') + "
        "(SELECT count(*) FROM brand_attention_daily WHERE parent_ticker='CAVA' "
        "OR brand ILIKE '%cava%')"),
}

# Numbers recorded in tests/expected_values.md (the only values this file may pre-fill), in the
# units check_verification.py expects: full USD, capex as a positive amount, comps in percent,
# CPI in index points, views as counts.
EXPECTED_VALUES = {
    "sec:YUM:total_assets:instant:2025": "8197000000",
    "sec:DRI:op_cash_flow:YTD9:2025": "1250000000",
    "sec:DRI:op_cash_flow:YTD6:2025": "661800000",
    "sec:CMG:capex:FY:2025": "666336000",
    "sec:CMG:capex:YTD9:2025": "468881000",
    "sec:CMG:operating_income:FY:2025": "1935798000",
    "sec:CMG:revenue:FY:2025": "11925601000",
    "sec:WING:operating_income:FY:2025": "179291000",
    "sec:WING:revenue:FY:2025": "696853000",
    "views:KFC:CY2025Q1": "266093",
    "views:Taco_Bell:CY2025Q1": "226860",
    "views:Pizza_Hut:CY2025Q1": "107956",
    "views:Habit_Burger_&_Grill:CY2025Q1": "19169",
    "views:The_Habit_Burger_Grill:CY2025Q1": "1302",
    "cpi:2024-12": "374.644",
    "cpi:2025-12": "389.889",
    "comps:CMG:2025Q1": "-0.4",
    "comps:WING:2025Q1": "0.5",
}

CQ = {"CY2024Q2": ("2024-04-01", "2024-06-30"), "CY2024Q4": ("2024-10-01", "2024-12-31"),
      "CY2025Q1": ("2025-01-01", "2025-03-31"), "CY2025Q2": ("2025-04-01", "2025-06-30"),
      "CY2025Q3": ("2025-07-01", "2025-09-30"), "CY2025Q4": ("2025-10-01", "2025-12-31")}

STATEMENT = {
    "total_assets": ("balance sheet", "total assets"),
    "revenue": ("income statement", "total revenues"),
    "operating_income": ("income statement", "income from operations / operating income"),
    "op_cash_flow": ("cash flow statement", "net cash provided by operating activities"),
    "capex": ("cash flow statement", "investing activities, purchases of property and equipment "
                                     "(capital expenditures)"),
}
COLUMN = {"Q": "three months ended", "YTD6": "six months ended", "YTD9": "nine months ended",
          "FY": "fiscal year ended", "instant": "as of"}


def d(x):
    return x.strftime("%b %d, %Y").replace(" 0", " ")


def sec_row(t, m, fy, basis):
    """Metadata only: no value column is selected."""
    sql = ("SELECT cik, concept, form, accession, period_start, period_end FROM fundamentals "
           "WHERE ticker=? AND metric=? AND fiscal_year=? AND period_basis=?")
    params = [t, m, fy, basis]
    if basis == "instant":
        sql += " AND fiscal_quarter=4"
    elif basis == "Q":
        sql += " AND fiscal_quarter=1"
    rows = con.execute(sql, params).fetchall()
    if len(rows) != 1:
        sys.exit(f"STOP: expected 1 row for {t} {m} FY{fy} {basis}, got {len(rows)}")
    cik, concept, form, acc, ps, pe = rows[0]
    filing_end = con.execute("SELECT max(period_end) FROM fundamentals WHERE accession=?",
                             [acc]).fetchone()[0]
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
    stmt, line = STATEMENT[m]
    if m == "op_cash_flow" and "ContinuingOperations" in concept:
        line += " of continuing operations"
    where = (f"{form} (accession {acc}), {stmt}, {line} (XBRL {concept}), "
             f"{COLUMN[basis]} {d(pe)}")
    if basis == "Q":
        where += f" (fiscal Q1 {fy}; the Q1 10-Q's only cash-flow column)" \
            if m in ("op_cash_flow", "capex") else f" (fiscal Q1 {fy})"
    notes = ["enter full USD: apply the statement's scale (thousands or millions)"]
    if m == "capex":
        notes.append("enter as a positive amount even though the statement prints it in parentheses")
    if pe < filing_end:
        where += (f"; PRIOR-YEAR COMPARATIVE column of a later filing (that filing's own period "
                  f"ends {d(filing_end)})")
        notes.append("the database cites this later filing; the value was first reported in the "
                     "filing for the period itself, which should print the same number")
    key = f"sec:{t}:{m}:{basis}:{fy}"
    return f"[sec:{t}:{m}:{basis}:FY{fy}]", url, where, notes, key


def comps_row(t, fy, fq):
    rows = con.execute("SELECT source_url, definition_id FROM comps_quarterly WHERE ticker=? "
                       "AND fiscal_year=? AND fiscal_quarter=?", [t, fy, fq]).fetchall()
    if len(rows) != 1:
        sys.exit(f"STOP: expected 1 comps row for {t} FY{fy}Q{fq}")
    url, def_id = rows[0]
    basis = "FY" if fq == 4 else "Q"
    qend = con.execute("SELECT period_end FROM fundamentals WHERE ticker=? AND fiscal_year=? "
                       "AND fiscal_quarter=? AND period_basis=? AND metric='revenue'",
                       [t, fy, fq, basis]).fetchone()[0]
    label = {"CMG": "headline comparable restaurant sales change",
             "WING": "headline domestic same store sales growth (franchised and company-owned "
                     "together; not the company-owned-only figure)"}[t]
    where = (f"8-K Exhibit 99.1 earnings release, {label}, fiscal Q{fq} {fy} "
             f"(quarter ended {d(qend)}); definition {def_id}")
    return (f"[comps:{t}:FY{fy}Q{fq}]", url, where,
            ["enter in percent as printed, negative for a decrease (-0.4 means a 0.4% decline)"],
            f"comps:{t}:{fy}Q{fq}")


def cpi_row(m):
    y, mo = m.split("-")
    where = (f"BLS CUSR0000SEFV (CPI-U food away from home, U.S. city average, seasonally "
             f"adjusted, 1982-84=100), data table row {y}, column {date(int(y), int(mo), 1):%b}; "
             f"also data/raw/macro/bls_CUSR0000SEFV.xlsx")
    return (f"[cpi:{m}]", "https://data.bls.gov/timeseries/CUSR0000SEFV", where,
            ["enter the index level as printed (3 decimals)"], f"cpi:{m}")


def census_row(m):
    y, mo = m.split("-")
    where = (f"Census Monthly Retail Trade, NAICS 722 food services and drinking places, U.S. "
             f"total, seasonally adjusted monthly sales, {date(int(y), int(mo), 1):%b %Y}; also "
             f"data/raw/macro/census_naics722_sa.xlsx")
    return (f"[census722:{m}]", "https://www.census.gov/econ/currentdata/", where,
            ["on the page choose Advance/Monthly Retail Trade (MRTS), 722 Food Services and "
             "Drinking Places, Sales - Monthly, U.S., seasonally adjusted",
             "enter millions of USD as printed",
             "values are the 2026-10-15 release; a later revision may differ"], f"census722:{m}")


def views_row(article, q):
    s, e = CQ[q]
    url = ("https://pageviews.wmcloud.org/?project=en.wikipedia.org&platform=all-access"
           f"&agent=user&redirects=0&start={s}&end={e}&pages={quote(article, safe='')}")
    where = (f"Pageviews Analysis, en.wikipedia.org, all-access, user agent, redirects off, "
             f"article {article}, {s} to {e}, summary table Views column (not daily average)")
    notes = ["enter the total views as an integer"]
    if article == "Habit_Burger_&_Grill" and s < "2024-08-29":
        notes.append("title starts 2024-08-29; views before that are under the former title")
    return f"[views:{article}:{q}]", url, where, notes, f"views:{article}:{q}"


def rows_for(q):
    text = q["question"]
    if q["expected_behavior"] == "refuse":
        if text not in ABSENT:
            sys.exit(f"STOP: no absence check for refusal question {q['id']}: {text}")
        what, desc, sql = ABSENT[text]
        return [(f"[absent:{what}]", "data/warehouse.duckdb (read_only)",
                 f"[absent:{what}] Confirm absent: {desc}",
                 [f"run read-only: duckdb.connect('data/warehouse.duckdb', read_only=True)"
                  f".sql(\"{sql}\"); enter the count it returns in value_seen (0 = absent)"],
                 f"absent:{what}")]
    if text not in PIECES:
        sys.exit(f"STOP: no pieces mapped for {q['id']}: {text}")
    out = []
    for p in PIECES[text]:
        kind = p[0]
        if kind == "sec":
            out.append(sec_row(*p[1:]))
        elif kind == "comps":
            out.append(comps_row(*p[1:]))
        elif kind == "cpi":
            out.append(cpi_row(p[1]))
        elif kind == "census722":
            out.append(census_row(p[1]))
        elif kind == "views":
            out.append(views_row(*p[1:]))
    return [(tag, url, f"{tag} {where}", notes, key) for tag, url, where, notes, key in out]


def section(q, rows):
    if q["question"] in REPLACEMENTS:
        return 0
    if q["expected_behavior"] == "refuse":
        return 5
    tag = rows[0][0]
    return {"[sec": 1, "[com": 2, "[cpi": 3, "[cen": 3, "[vie": 4}[tag[:4]]


def main():
    questions = yaml.safe_load(QUESTIONS.read_text())
    kept = {}
    if OUT.exists():
        with OUT.open(newline="") as f:
            for r in csv.DictReader(f):
                kept[(r["question_id"], r["where_in_source"].split("]")[0] + "]")] = r

    built = []
    for q in questions:
        rows = rows_for(q)
        sec_ = section(q, rows)
        for i, (tag, url, where, notes, key) in enumerate(rows):
            value = ""
            if key in EXPECTED_VALUES:
                value = EXPECTED_VALUES[key]
                notes = notes + ["from expected_values.md"]
            old = kept.get((q["id"], tag))
            if old and old["value_seen"].strip() and not value:
                value = old["value_seen"]
            built.append((sec_, q["id"], i, {
                "question_id": q["id"], "source_url": url, "where_in_source": where,
                "value_seen": value, "matches": "", "notes": "; ".join(notes)}))

    built.sort(key=lambda b: (b[0], b[1], b[2]))
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for *_, row in built:
            w.writerow(row)

    names = ["replacement questions", "SEC", "comps", "macro", "pageviews", "refusals"]
    total = len(built)
    prefilled = sum(1 for b in built if b[3]["value_seen"])
    print(f"Wrote {OUT.relative_to(ROOT)}: {total} rows for {len(questions)} questions")
    for i, n in enumerate(names):
        rs = [b for b in built if b[0] == i]
        print(f"  {n:22s} {len(rs):4d} rows, {sum(1 for b in rs if not b[3]['value_seen']):4d} to fill")
    print(f"Pre-filled from tests/expected_values.md: {prefilled}")
    print(f"Rows you need to fill (value_seen blank): {total - prefilled}")
    if not REPLACEMENTS:
        print("Note: no replacement questions yet; questions.yaml has "
              f"{len(questions)} of 42.")


if __name__ == "__main__":
    main()
