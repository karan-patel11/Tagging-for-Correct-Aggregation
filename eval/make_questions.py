"""Phase 9: build eval/questions.yaml and its answer key (SPEC.md §11.1-11.3).

Wording comes verbatim from eval/questions_draft.md. Correct and trap answers are computed here
with direct SQL against data/warehouse.duckdb opened read_only. This file must never import
semantics.py or anything from src/: the code under test may not grade itself.

For each question it prints the XBRL concepts used (fundamentals questions) and any wording flags,
then selects 7 questions per category in draft order (main questions, then spares), skipping any
whose trap answer is within 2x the §11.6 tolerance of the correct answer. Skipped questions stay in
the draft for history. IDs are stable (see IDS); it stops if a category ends up short, or if a
replacement question fails the 2x rule.

Run: python eval/make_questions.py
"""

import re
import sys
from pathlib import Path

import duckdb
import yaml

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "warehouse.duckdb"
DRAFT = ROOT / "eval" / "questions_draft.md"
OUT = ROOT / "eval" / "questions.yaml"

CATEGORIES = ["time_additivity", "ratios", "ytd_calendar", "indices", "hierarchy",
              "comparability_unanswerable"]
PER_CATEGORY = 7

# Wording edits allowed by §11.1 (name a missing period or unit), keyed by (category, draft number).
# Every entry is printed. None were needed: every draft question already names its period and unit.
WORDING_EDITS = {}

con = duckdb.connect(str(DB_PATH), read_only=True)


# ---------------------------------------------------------------------------------------------
# Draft parsing
# ---------------------------------------------------------------------------------------------

def parse_draft():
    """Return {category: [(section, number, text), ...]} in draft order, wording untouched.
    section is "main" or "spare"; any number of questions per category is accepted."""
    out = {c: [] for c in CATEGORIES}
    section, cat = None, None
    for line in DRAFT.read_text().splitlines():
        if line.startswith("## Spares"):
            section, cat = "spare", None
            continue
        if line.startswith("## Changes"):
            section = None
            continue
        m = re.match(r"^## (\w+)\s*$", line)
        if m and m.group(1) in CATEGORIES:
            section, cat = "main", m.group(1)
            continue
        m = re.match(r"^(\w+):\s*$", line)
        if section == "spare" and m and m.group(1) in CATEGORIES:
            cat = m.group(1)
            continue
        m = re.match(r"^(\d+)\.\s+(.*\S)\s*$", line)
        if m and section and cat:
            out[cat].append((section, int(m.group(1)), m.group(2)))
    # Main questions first, then spares, each in draft order.
    for cat in CATEGORIES:
        out[cat].sort(key=lambda x: (x[0] != "main",))
    return out


# ---------------------------------------------------------------------------------------------
# Data access (direct SQL only)
# ---------------------------------------------------------------------------------------------

def fact(ticker, metric, fy, basis, fq=None):
    """One fundamentals row as a dict; fails loudly if it is missing or not unique."""
    sql = ("SELECT value, concept, accession, form, period_start, period_end FROM fundamentals "
           "WHERE ticker=? AND metric=? AND fiscal_year=? AND period_basis=?")
    params = [ticker, metric, fy, basis]
    if fq is not None:
        sql += " AND fiscal_quarter=?"
        params.append(fq)
    rows = con.execute(sql, params).fetchall()
    if len(rows) != 1:
        sys.exit(f"STOP: expected 1 row for {ticker} {metric} FY{fy} {basis} Q{fq}, got {len(rows)}")
    v, concept, acc, form, ps, pe = rows[0]
    return {"value": v, "concept": concept, "accession": acc, "form": form,
            "start": ps, "end": pe}


def src(row, what):
    span = f"{row['start']} to {row['end']}" if row["start"] else f"as of {row['end']}"
    return f"{row['accession']} ({row['form']}), {what}, {span}"


def quarter(ticker, metric, fy, q):
    """Single fiscal quarter: filed Q row if present, else the YTD difference. Returns
    (value, [rows used], description)."""
    if q in (1, 2, 3):
        rows = con.execute(
            "SELECT count(*) FROM fundamentals WHERE ticker=? AND metric=? AND fiscal_year=? "
            "AND fiscal_quarter=? AND period_basis='Q'", [ticker, metric, fy, q]).fetchone()[0]
        if rows:
            r = fact(ticker, metric, fy, "Q", q)
            return r["value"], [r], [src(r, f"three-month column (Q{q})")]
    prior = {1: None, 2: ("Q", 1), 3: ("YTD6", 2), 4: ("YTD9", 3)}[q]
    cur = {2: ("YTD6", 2), 3: ("YTD9", 3), 4: ("FY", 4)}[q]
    a = fact(ticker, metric, fy, *cur)
    b = fact(ticker, metric, fy, *prior)
    return (a["value"] - b["value"], [a, b],
            [src(a, f"{cur[0]} column"), src(b, f"{prior[0]} column, subtracted")])


def views(tickers_brand_filter, start, end, include_parent=False):
    grains = "('brand','parent')" if include_parent else "('brand')"
    return con.execute(
        f"SELECT sum(views) FROM brand_attention_daily WHERE grain IN {grains} "
        f"AND {tickers_brand_filter} AND date BETWEEN ? AND ?", [start, end]).fetchone()[0]


def macro(series, month):
    rows = con.execute("SELECT value FROM macro_monthly WHERE series_id=? AND date=?",
                       [series, month]).fetchall()
    if len(rows) != 1:
        sys.exit(f"STOP: expected 1 macro row for {series} {month}, got {len(rows)}")
    return rows[0][0]


def macro_sum(series, months):
    return sum(macro(series, m) for m in months)


CQ = {"CY2024Q2": ("2024-04-01", "2024-06-30"), "CY2024Q3": ("2024-07-01", "2024-09-30"),
      "CY2024Q4": ("2024-10-01", "2024-12-31"), "CY2025Q1": ("2025-01-01", "2025-03-31"),
      "CY2025Q2": ("2025-04-01", "2025-06-30"), "CY2025Q3": ("2025-07-01", "2025-09-30"),
      "CY2025": ("2025-01-01", "2025-12-31")}
MONTHS = {"CY2024Q3": ["2024-07-01", "2024-08-01", "2024-09-01"],
          "CY2025Q1": ["2025-01-01", "2025-02-01", "2025-03-01"],
          "CY2025Q2": ["2025-04-01", "2025-05-01", "2025-06-01"],
          "CY2024Q4": ["2024-10-01", "2024-11-01", "2024-12-01"]}
CPI, FOOD = "CUSR0000SEFV", "CENSUS_722_SA"
YUM_BRANDS = "parent_ticker='YUM'"
DRI_BRANDS = "parent_ticker='DRI'"


# ---------------------------------------------------------------------------------------------
# Question builders. Each returns a dict with expected_behavior, correct, unit, tolerance kind,
# trap_answers, verified_against, notes, and concepts [(ticker, metric, concept)].
# ---------------------------------------------------------------------------------------------

def q_assets(ticker, fy):
    rows = [fact(ticker, "total_assets", fy, "instant", q) for q in (1, 2, 3, 4)]
    vals = [r["value"] for r in rows]
    return dict(expected_behavior="answer", correct=vals[3], unit="USD", tol="USD",
                trap_answers={"sum_of_4_quarter_ends": sum(vals),
                              "mean_of_4_quarter_ends": sum(vals) / 4},
                verified_against=src(rows[3], "balance sheet, Total assets"),
                concepts=[(ticker, "total_assets", rows[3]["concept"])])


def q_eps(ticker, fy):
    fy_row = fact(ticker, "diluted_eps", fy, "FY")
    qs = [quarter(ticker, "diluted_eps", fy, q)[0] for q in (1, 2, 3, 4)]
    return dict(expected_behavior="answer", correct=fy_row["value"], unit="USD/shares", tol="EPS",
                trap_answers={"sum_of_4_quarters": sum(qs), "mean_of_4_quarters": sum(qs) / 4},
                verified_against=src(fy_row, "income statement, diluted EPS, fiscal-year column"),
                notes="Q4 EPS is not filed in XBRL; the trap's Q4 is FY minus YTD9.",
                concepts=[(ticker, "diluted_eps", fy_row["concept"])])


def q_combined_margin(pairs, warning=False):
    """pairs: [(ticker, fy)]. Correct = sum(op income) / sum(revenue) * 100."""
    oi = [fact(t, "operating_income", fy, "FY") for t, fy in pairs]
    rev = [fact(t, "revenue", fy, "FY") for t, fy in pairs]
    margins = [o["value"] / r["value"] * 100 for o, r in zip(oi, rev)]
    correct = sum(o["value"] for o in oi) / sum(r["value"] for r in rev) * 100
    ver = "; ".join(f"{t} FY{fy}: " + src(o, "income statement, operating income and revenue")
                    for (t, fy), o in zip(pairs, oi))
    concepts = []
    for (t, _), o, r in zip(pairs, oi, rev):
        concepts += [(t, "operating_income", o["concept"]), (t, "revenue", r["concept"])]
    out = dict(expected_behavior="answer_with_warning" if warning else "answer",
               correct=correct, unit="percent", tol="percent",
               trap_answers={"mean_of_margins": sum(margins) / len(margins)},
               verified_against=ver, concepts=concepts)
    if warning:
        out["notes"] = ("Mixes Darden's May fiscal year with December fiscal years; the expected "
                        "warning is the fiscal-calendar mismatch.")
    return out


def q_annual_margin(ticker, fy):
    oi_fy, rev_fy = fact(ticker, "operating_income", fy, "FY"), fact(ticker, "revenue", fy, "FY")
    qm = [quarter(ticker, "operating_income", fy, q)[0] / quarter(ticker, "revenue", fy, q)[0] * 100
          for q in (1, 2, 3, 4)]
    return dict(expected_behavior="answer", correct=oi_fy["value"] / rev_fy["value"] * 100,
                unit="percent", tol="percent",
                trap_answers={"mean_of_quarterly_margins": sum(qm) / 4},
                verified_against=src(oi_fy, "income statement, operating income and revenue, "
                                            "fiscal-year column"),
                concepts=[(ticker, "operating_income", oi_fy["concept"]),
                          (ticker, "revenue", rev_fy["concept"])])


def q_single_quarter(ticker, metric, fy, q, wrong_fy=None):
    val, rows, desc = quarter(ticker, metric, fy, q)
    # Raw YTD trap: the filed YTD value for the quarter asked (Q4 has none, so YTD9).
    ytd_basis = {2: "YTD6", 3: "YTD9", 4: "YTD9"}[q]
    traps = {f"used_{ytd_basis.lower()}_value": fact(ticker, metric, fy, ytd_basis)["value"]}
    traps["used_fy_value"] = fact(ticker, metric, fy, "FY")["value"]
    if wrong_fy is not None:
        traps[f"used_fiscal_{wrong_fy}"] = quarter(ticker, metric, wrong_fy, q)[0]
    return dict(expected_behavior="answer", correct=val, unit="USD", tol="USD",
                trap_answers=traps, verified_against="; ".join(desc),
                concepts=[(ticker, metric, rows[0]["concept"])])


def q_food_months(months, wrong):
    """Sum of monthly Census 722 SA values (millions); wrong = {trap_name: months}."""
    traps = {name: macro_sum(FOOD, m) for name, m in wrong.items()}
    traps["average_instead_of_sum"] = macro_sum(FOOD, months) / len(months)
    return dict(expected_behavior="answer", correct=macro_sum(FOOD, months),
                unit="USD millions", tol="USD", trap_answers=traps,
                verified_against=f"data/raw/macro Census NAICS 722 SA file, months {', '.join(months)}")


def q_cpi_change(m0, m1):
    a, b = macro(CPI, m0), macro(CPI, m1)
    return dict(expected_behavior="answer", correct=(b / a - 1) * 100, unit="percent",
                tol="index_pct_change", trap_answers={"index_point_difference": b - a},
                verified_against=f"data/raw/macro BLS {CPI} file, {m0} and {m1}")


def q_cpi_avg(year):
    months = [f"{year}-{m:02d}-01" for m in range(1, 13)]
    vals = [macro(CPI, m) for m in months]
    return dict(expected_behavior="answer", correct=sum(vals) / 12, unit="index_points",
                tol="index_points", trap_answers={"sum_of_index_levels": sum(vals)},
                verified_against=f"data/raw/macro BLS {CPI} file, Jan-Dec {year}")


def q_views(brand_filter, period):
    s, e = CQ[period]
    return dict(expected_behavior="answer", correct=views(brand_filter, s, e), unit="views",
                tol="views",
                trap_answers={"included_parent_rows": views(brand_filter, s, e, True)},
                verified_against=f"brand_attention_daily, grain='brand', {brand_filter}, {s} to {e}")


def q_kfc_share(period):
    s, e = CQ[period]
    kfc = views("brand='KFC'", s, e)
    return dict(expected_behavior="answer", correct=kfc / views(YUM_BRANDS, s, e) * 100,
                unit="percent", tol="percent",
                trap_answers={"included_parent_rows":
                              kfc / views(YUM_BRANDS, s, e, True) * 100},
                verified_against=f"brand_attention_daily, KFC over YUM brand rows, {s} to {e}")


def q_comps_diff(fq):
    rows = {t: con.execute("SELECT comp_sales_pct, definition_id, source_url FROM comps_quarterly "
                           "WHERE ticker=? AND fiscal_year=2025 AND fiscal_quarter=?",
                           [t, fq]).fetchall() for t in ("CMG", "WING")}
    for t, r in rows.items():
        if len(r) != 1:
            sys.exit(f"STOP: expected 1 comps row for {t} FY2025 Q{fq}, got {len(r)}")
    cmg, wing = rows["CMG"][0], rows["WING"][0]
    return dict(expected_behavior="answer_with_warning", correct=cmg[0] - wing[0],
                unit="percentage_points", tol="percent", trap_answers={},
                verified_against=f"CMG {cmg[2]}; WING {wing[2]}",
                notes=(f"CMG {cmg[0]} minus WING {wing[0]}. Definitions differ ({cmg[1]} vs "
                       f"{wing[1]}). The trap is behavioral (a confident answer with no warning), "
                       "so no numeric trap is stored."))


def q_refuse(unit, reason, check_sql):
    n = con.execute(check_sql).fetchone()[0]
    if n:
        sys.exit(f"STOP: refusal question has data ({n} rows): {check_sql}")
    return dict(expected_behavior="refuse", correct=None, unit=unit, tol=None, trap_answers={},
                verified_against=f"absent from warehouse: {check_sql} returns 0",
                notes=reason + " The trap is any confident single answer (behavioral).")


# Builders keyed by (category, draft section, draft number).
BUILDERS = {
    ("time_additivity", "main", 1): lambda: q_assets("CMG", 2025),
    ("time_additivity", "main", 2): lambda: q_assets("WING", 2025),
    ("time_additivity", "main", 3): lambda: q_assets("YUM", 2025),
    ("time_additivity", "main", 4): lambda: q_assets("DRI", 2025),
    ("time_additivity", "main", 5): lambda: q_assets("YUM", 2024),
    ("time_additivity", "main", 6): lambda: q_eps("CMG", 2025),
    ("time_additivity", "main", 7): lambda: q_eps("WING", 2025),
    ("time_additivity", "main", 8): lambda: q_assets("CMG", 2024),
    ("time_additivity", "spare", 1): lambda: q_eps("CMG", 2024),
    ("time_additivity", "spare", 2): lambda: q_eps("YUM", 2025),
    ("time_additivity", "spare", 3): lambda: q_assets("WING", 2024),
    ("ratios", "main", 1): lambda: q_combined_margin([("CMG", 2025), ("WING", 2025)]),
    ("ratios", "main", 2): lambda: q_combined_margin([("CMG", 2025), ("YUM", 2025)]),
    ("ratios", "main", 3): lambda: q_combined_margin([("CMG", 2025), ("WING", 2025), ("YUM", 2025)]),
    ("ratios", "main", 4): lambda: q_annual_margin("CMG", 2025),
    ("ratios", "main", 5): lambda: q_annual_margin("YUM", 2025),
    ("ratios", "main", 6): lambda: q_annual_margin("DRI", 2025),
    ("ratios", "main", 7): lambda: q_combined_margin([("CMG", 2025), ("YUM", 2025), ("DRI", 2025)],
                                                     warning=True),
    ("ratios", "main", 8): lambda: q_combined_margin([("CMG", 2024), ("WING", 2024)]),
    ("ratios", "main", 9): lambda: q_combined_margin([("CMG", 2024), ("YUM", 2024)]),
    ("ratios", "spare", 1): lambda: q_combined_margin([("WING", 2025), ("YUM", 2025)]),
    ("ratios", "spare", 2): lambda: q_annual_margin("WING", 2025),
    ("ratios", "spare", 3): lambda: q_annual_margin("CMG", 2024),
    ("ytd_calendar", "main", 1): lambda: q_single_quarter("CMG", "op_cash_flow", 2025, 2),
    ("ytd_calendar", "main", 2): lambda: q_single_quarter("YUM", "op_cash_flow", 2025, 3),
    ("ytd_calendar", "main", 3): lambda: q_single_quarter("CMG", "capex", 2025, 4),
    ("ytd_calendar", "main", 4): lambda: q_single_quarter("WING", "capex", 2025, 4),
    ("ytd_calendar", "main", 5): lambda: q_single_quarter("DRI", "op_cash_flow", 2025, 3,
                                                          wrong_fy=2026),
    ("ytd_calendar", "main", 6): lambda: q_single_quarter("DRI", "revenue", 2026, 4, wrong_fy=2025),
    ("ytd_calendar", "main", 7): lambda: q_food_months(
        ["2024-12-01", "2025-01-01", "2025-02-01"],
        {"wrong_months_calendar_q1_2025": MONTHS["CY2025Q1"],
         "wrong_months_calendar_q4_2024": MONTHS["CY2024Q4"]}),
    ("ytd_calendar", "main", 8): lambda: q_single_quarter("YUM", "op_cash_flow", 2025, 4),
    ("indices", "main", 1): lambda: q_cpi_change("2024-12-01", "2025-12-01"),
    ("indices", "main", 2): lambda: q_cpi_change("2024-06-01", "2025-06-01"),
    ("indices", "main", 3): lambda: q_cpi_avg(2024),
    ("indices", "main", 4): lambda: q_cpi_change("2024-12-01", "2025-06-01"),
    ("indices", "main", 5): lambda: q_food_months(MONTHS["CY2024Q3"], {}),
    ("indices", "main", 6): lambda: q_food_months(MONTHS["CY2025Q1"], {}),
    ("indices", "main", 7): lambda: q_food_months(MONTHS["CY2025Q2"], {}),
    ("hierarchy", "main", 1): lambda: q_views(YUM_BRANDS, "CY2024Q4"),
    ("hierarchy", "main", 2): lambda: q_views(YUM_BRANDS, "CY2025Q1"),
    ("hierarchy", "main", 3): lambda: q_views(YUM_BRANDS, "CY2025Q2"),
    ("hierarchy", "main", 4): lambda: q_views(DRI_BRANDS, "CY2024Q2"),
    ("hierarchy", "main", 5): lambda: q_views(DRI_BRANDS, "CY2025Q3"),
    ("hierarchy", "main", 6): lambda: q_kfc_share("CY2025"),
    ("hierarchy", "main", 7): lambda: q_kfc_share("CY2024Q4"),
    ("comparability_unanswerable", "main", 1): lambda: q_comps_diff(1),
    ("comparability_unanswerable", "main", 2): lambda: q_comps_diff(2),
    ("comparability_unanswerable", "main", 3): lambda: q_comps_diff(4),
    ("comparability_unanswerable", "main", 4): lambda: q_refuse(
        "USD", "Average unit volume is not in the data.",
        "SELECT count(*) FROM fundamentals WHERE metric ILIKE '%unit_volume%' "
        "OR metric ILIKE '%auv%'"),
    ("comparability_unanswerable", "main", 5): lambda: q_refuse(
        "count", "Restaurant counts are not in the data.",
        "SELECT count(*) FROM fundamentals WHERE metric ILIKE '%restaurant%' "
        "OR metric ILIKE '%unit_count%'"),
    ("comparability_unanswerable", "main", 6): lambda: q_refuse(
        "USD", "Fiscal 2023 is outside the window (CMG fiscal 2024-2025).",
        "SELECT count(*) FROM fundamentals WHERE ticker='CMG' AND fiscal_year=2023"),
    ("comparability_unanswerable", "main", 7): lambda: q_refuse(
        "percent", "CAVA is not in the data.",
        "SELECT (SELECT count(*) FROM comps_quarterly WHERE ticker='CAVA') + "
        "(SELECT count(*) FROM fundamentals WHERE ticker='CAVA')"),
}

# Stable question IDs. The first 38 were assigned in the first build and never change; questions
# added later take the next free ID. A selected question without an ID stops the build.
IDS = {
    ("time_additivity", "main", 1): "q001", ("time_additivity", "main", 2): "q002",
    ("time_additivity", "main", 3): "q003", ("time_additivity", "main", 4): "q004",
    ("time_additivity", "main", 5): "q005", ("time_additivity", "spare", 3): "q006",
    ("ratios", "main", 1): "q007", ("ratios", "main", 2): "q008", ("ratios", "main", 3): "q009",
    ("ratios", "main", 7): "q010", ("ratios", "spare", 1): "q011",
    **{("ytd_calendar", "main", n): f"q{11 + n:03d}" for n in range(1, 7)},
    **{("indices", "main", n): f"q{17 + n:03d}" for n in range(1, 8)},
    **{("hierarchy", "main", n): f"q{24 + n:03d}" for n in range(1, 8)},
    **{("comparability_unanswerable", "main", n): f"q{31 + n:03d}" for n in range(1, 8)},
    # Replacements, added 2026-10-27, after semantics.py existed.
    ("time_additivity", "main", 8): "q039", ("ratios", "main", 8): "q040",
    ("ratios", "main", 9): "q041", ("ytd_calendar", "main", 8): "q042",
}
# The 2x rule must pass for these; if one fails the build stops instead of skipping it.
MUST_PASS = {("time_additivity", "main", 8), ("ratios", "main", 8), ("ratios", "main", 9),
             ("ytd_calendar", "main", 8)}


# ---------------------------------------------------------------------------------------------
# Tolerances (SPEC §11.6) and the 2x-tolerance drop rule
# ---------------------------------------------------------------------------------------------

def tolerance(kind, correct):
    """Absolute tolerance, or None if §11.6 defines none for this unit."""
    return {"USD": 0.005 * abs(correct) if correct is not None else None,
            "percent": 0.1, "EPS": 0.01,
            "views": 0.001 * abs(correct) if correct is not None else None,
            "index_pct_change": 0.05, "index_points": 0.1}.get(kind)


def too_close(q):
    """List of (trap, gap, 2*tol) for traps within 2x tolerance. Rounds to 1e-9 to avoid
    float noise deciding a boundary case."""
    tol = tolerance(q["tol"], q["correct"])
    if tol is None:
        return []
    return [(name, abs(v - q["correct"]), 2 * tol) for name, v in q["trap_answers"].items()
            if round(abs(v - q["correct"]), 9) <= round(2 * tol, 9)]


# ---------------------------------------------------------------------------------------------
# Wording checks against the XBRL concept (fundamentals questions)
# ---------------------------------------------------------------------------------------------

def concept_flags(text, concepts):
    flags = []
    low = text.lower()
    for ticker, metric, concept in concepts:
        cont = "ContinuingOperations" in concept
        if "continuing operations" in low and not cont:
            flags.append(f"{ticker} {metric}: question says continuing operations, "
                         f"concept {concept} is total (incl. discontinued)")
        if cont and "continuing operations" not in low:
            flags.append(f"{ticker} {metric}: concept {concept} is continuing operations only, "
                         "question does not say so")
        if metric == "capex":
            flags.append(f"{ticker} capex: question says 'capital expenditure', concept is "
                         f"{concept} (purchases of PP&E only; excludes acquisitions, "
                         "capitalized software if tagged separately)")
    revenue_concepts = {c for _, m, c in concepts if m == "revenue"}
    if len(revenue_concepts) > 1:
        flags.append(f"revenue concepts differ across companies: {sorted(revenue_concepts)}")
    return flags


def fmt(v):
    if v is None:
        return "null"
    return f"{v:,.6f}".rstrip("0").rstrip(".") if abs(v) < 1000 else f"{v:,.2f}"


def clean(v, kind):
    if v is None:
        return None
    if kind in ("USD",) and float(v).is_integer():
        return int(v)
    if kind == "views":
        return int(v)
    return round(float(v), 6)


def main():
    draft = parse_draft()
    for cat in CATEGORIES:
        for section, n, _ in draft[cat]:
            if (cat, section, n) not in BUILDERS:
                sys.exit(f"STOP: no builder for {cat} {section} #{n}")

    print("=== Wording edits (SPEC §11.1: only a missing period or unit) ===")
    if not WORDING_EDITS:
        print("None made by this script; wording is verbatim from the draft.")
    for (cat, n), (old, new) in WORDING_EDITS.items():
        print(f"{cat} #{n}: {old!r} -> {new!r}")

    kept, dropped, unused = {c: [] for c in CATEGORIES}, [], []
    concept_rows = []

    for cat in CATEGORIES:
        for section, n, text in draft[cat]:
            key = (cat, section, n)
            label = f"{cat} {'#' if section == 'main' else 'spare #'}{n}"
            if len(kept[cat]) >= PER_CATEGORY:
                unused.append(label)
                continue
            q = BUILDERS[key]()
            q["category"], q["question"], q["label"], q["key"] = cat, text, label, key
            for t, m, c in q.get("concepts", []):
                concept_rows.append((label, t, m, c))
            q["flags"] = concept_flags(text, q.get("concepts", []))
            close = too_close(q)
            if close and key in MUST_PASS:
                for name, gap, lim in close:
                    print(f"{label}: trap {name} gap {fmt(gap)} <= 2x tol {fmt(lim)}")
                sys.exit(f"STOP: replacement question {label} fails the 2x rule: {text}")
            if close:
                dropped.append((q, close))
                continue
            if key not in IDS:
                sys.exit(f"STOP: selected question {label} has no ID: {text}")
            q["id"] = IDS[key]
            kept[cat].append(q)

    print("\n=== XBRL concepts used per fundamentals question ===")
    for label, t, m, c in concept_rows:
        print(f"{label:34s} {t:5s} {m:17s} {c}")

    print("\n=== Wording vs concept flags ===")
    any_flag = False
    for cat in CATEGORIES:
        for q in kept[cat] + [d[0] for d in dropped if d[0]["category"] == cat]:
            for f in q["flags"]:
                any_flag = True
                print(f"{q['label']}: {f}")
    if not any_flag:
        print("None.")

    print("\n=== Dropped (kept in the draft for history): a trap within 2x tolerance ===")
    if not dropped:
        print("None.")
    for q, close in dropped:
        for name, gap, lim in close:
            print(f"{q['label']}: trap {name} = {fmt(q['trap_answers'][name])}, correct = "
                  f"{fmt(q['correct'])}, gap {fmt(gap)} <= 2x tol {fmt(lim)}")
        print(f"    {q['question']}")
    print("\nNot evaluated (category already had 7): " + (", ".join(unused) or "none"))

    print("\n=== Counts per category ===")
    short = False
    for cat in CATEGORIES:
        status = "OK" if len(kept[cat]) == PER_CATEGORY else f"SHORT by {PER_CATEGORY - len(kept[cat])}"
        short |= len(kept[cat]) < PER_CATEGORY
        print(f"{cat:27s} {len(kept[cat])}  {status}")
    if short:
        sys.exit("STOP: a category has fewer than 7 questions; questions.yaml not written.")

    ids = [q["id"] for c in CATEGORIES for q in kept[c]]
    if len(set(ids)) != len(ids):
        sys.exit(f"STOP: duplicate IDs {ids}")

    out = []
    for q in sorted((q for c in CATEGORIES for q in kept[c]), key=lambda q: q["id"]):
        out.append({
            "id": q["id"], "category": q["category"], "question": q["question"],
            "expected_behavior": q["expected_behavior"],
            "correct": clean(q["correct"], q["tol"]), "unit": q["unit"],
            "trap_answers": {k: clean(v, q["tol"]) for k, v in q["trap_answers"].items()},
            "verified_against": q["verified_against"],
            "notes": "; ".join(filter(None, [q.get("notes", ""), *q["flags"]])),
        })

    old = {q["id"]: q for q in yaml.safe_load(OUT.read_text())} if OUT.exists() else {}
    print("\n=== Changes against the previous questions.yaml ===")
    for q in out:
        prev = old.get(q["id"])
        if prev is None:
            print(f"NEW {q['id']} ({q['category']}): {q['question']}")
            continue
        for field in q:
            if q[field] != prev.get(field):
                print(f"{q['id']} {field}:\n    before: {prev.get(field)!r}\n    after:  {q[field]!r}")
    for qid in sorted(set(old) - {q["id"] for q in out}):
        print(f"REMOVED {qid}")

    OUT.write_text("# Generated by eval/make_questions.py from eval/questions_draft.md. Do not edit "
                   "by hand;\n# correct and trap answers are computed with direct SQL "
                   "(no semantics.py).\n"
                   + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=100))

    print("\n=== Answer key ===")
    for q in out:
        traps = ", ".join(f"{k}={fmt(v)}" for k, v in q["trap_answers"].items()) or "-"
        print(f"{q['id']} {q['category']:27s} {q['expected_behavior']:20s} "
              f"{fmt(q['correct']):>20s} {q['unit']:18s} traps: {traps}")
    print(f"\n{len(out)} questions. Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
