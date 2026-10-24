"""Phase 1: SEC XBRL ingestion (SPEC.md §6.1-6.2).

Downloads companyfacts JSON for each ticker into data/raw/sec/, chooses one XBRL
concept per (ticker, metric), prints the coverage table, and writes the as-filed
rows to data/interim/fundamentals.parquet. Then runs the Phase 1 acceptance checks.

Run: python src/ingest_sec.py [--refresh]
"""

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "sec"
OUT_PATH = ROOT / "data" / "interim" / "fundamentals.parquet"
RETRIEVED_PATH = RAW_DIR / "retrieved.json"

TICKERS = ["CMG", "WING", "YUM", "DRI"]
FYE_MONTH = {"DRI": 5}  # everyone else is 12
WINDOW = {"CMG": [2024, 2025], "WING": [2024, 2025], "YUM": [2024, 2025], "DRI": [2025, 2026]}
FORMS = {"10-Q", "10-K"}

# metric -> (unit, candidate concepts in priority order)
CANDIDATES = {
    "revenue": ("USD", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"]),
    "operating_income": ("USD", ["OperatingIncomeLoss"]),
    "net_income": ("USD", ["NetIncomeLoss"]),
    "op_cash_flow": ("USD", ["NetCashProvidedByUsedInOperatingActivities",
                             "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "capex": ("USD", ["PaymentsToAcquirePropertyPlantAndEquipment"]),
    "total_assets": ("USD", ["Assets"]),
    "diluted_eps": ("USD/shares", ["EarningsPerShareDiluted"]),
}
INSTANT_METRICS = {"total_assets"}

# Period bases that count as covering a fiscal quarter, by fiscal quarter.
# Flows: Q1 needs a single quarter, Q2/Q3 a single quarter or the matching YTD, Q4 the FY row.
FLOW_COVER = {1: {"Q"}, 2: {"Q", "YTD6"}, 3: {"Q", "YTD9"}, 4: {"FY"}}

COLUMNS = ["ticker", "cik", "metric", "concept", "value", "unit", "period_start", "period_end",
           "period_basis", "fiscal_year", "fiscal_quarter", "form", "accession", "filed"]


def classify_basis(start, end):
    if pd.isna(start): return "instant"
    d = (end - start).days
    if 80 <= d <= 100:  return "Q"
    if 170 <= d <= 190: return "YTD6"
    if 260 <= d <= 285: return "YTD9"
    if 350 <= d <= 380: return "FY"
    return "other"   # log and inspect, never silently keep


def fiscal_labels(end, fye_month=12):
    adj = end - pd.Timedelta(days=7)          # handles year-ends falling in early January
    m = (adj.month - fye_month) % 12 or 12    # months into the fiscal year, 1..12
    fy = adj.year if adj.month <= fye_month else adj.year + 1
    return fy, (m + 2) // 3                   # fiscal year, fiscal quarter


def filing_url(cik, accession):
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{accession}-index.htm")


# ---------- download ----------

def user_agent():
    load_dotenv(ROOT / ".env")
    ua = os.environ.get("USER_AGENT", "").strip().strip('"')
    if not ua:
        sys.exit("USER_AGENT is not set. Copy .env.example to .env (SPEC.md §6.2).")
    return ua


def get_json(url, ua):
    r = requests.get(url, headers={"User-Agent": ua}, timeout=60)
    r.raise_for_status()
    time.sleep(0.2)
    return r.json()


def download(refresh):
    retrieved = json.loads(RETRIEVED_PATH.read_text()) if RETRIEVED_PATH.exists() else {}
    missing = [t for t in TICKERS if refresh or not (RAW_DIR / f"{t}.json").exists()]
    if not missing:
        return retrieved
    ua = user_agent()
    tickers = get_json("https://www.sec.gov/files/company_tickers.json", ua)
    cik_by_ticker = {v["ticker"]: v["cik_str"] for v in tickers.values()}
    for t in missing:
        if t not in cik_by_ticker:
            sys.exit(f"{t} not found in company_tickers.json")
        cik = f"{cik_by_ticker[t]:010d}"
        url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
        data = get_json(url, ua)
        (RAW_DIR / f"{t}.json").write_text(json.dumps(data))
        retrieved[t] = {"cik": cik, "url": url, "retrieved_on": date.today().isoformat()}
        print(f"downloaded {t} (CIK {cik})")
    RETRIEVED_PATH.write_text(json.dumps(retrieved, indent=2) + "\n")
    return retrieved


# ---------- parse ----------

def load_rows(ticker):
    """All 10-Q/10-K rows for every candidate concept, with basis and fiscal labels."""
    facts = json.loads((RAW_DIR / f"{ticker}.json").read_text())
    cik = f"{int(facts['cik']):010d}"
    gaap = facts["facts"].get("us-gaap", {})
    rows = []
    for metric, (unit, concepts) in CANDIDATES.items():
        for concept in concepts:
            for f in gaap.get(concept, {}).get("units", {}).get(unit, []):
                if f.get("form") not in FORMS:
                    continue
                rows.append({
                    "ticker": ticker, "cik": cik, "metric": metric, "concept": concept,
                    "value": float(f["val"]), "unit": unit,
                    "period_start": f.get("start"), "period_end": f["end"],
                    "form": f["form"], "accession": f["accn"], "filed": f["filed"],
                })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for c in ["period_start", "period_end", "filed"]:
        df[c] = pd.to_datetime(df[c])
    df["period_basis"] = [classify_basis(s, e) for s, e in zip(df.period_start, df.period_end)]
    labels = [fiscal_labels(e, FYE_MONTH.get(ticker, 12)) for e in df.period_end]
    df["fiscal_year"] = [fy for fy, _ in labels]
    df["fiscal_quarter"] = [fq for _, fq in labels]
    return df[df.fiscal_year.isin(WINDOW[ticker])]


def dedupe(df):
    """One row per date-based key (§6.2 rule 3). Never key on fiscal labels.

    Duration facts keep the latest-filed row (post-split EPS); instant (balance-sheet)
    facts keep the earliest-filed row (as originally reported). Prints every key
    where filings disagree on value.
    """
    df = df.copy()
    df["_start"] = df.period_start.fillna(pd.Timestamp(0))
    key = ["ticker", "metric", "concept", "_start", "period_end"]
    df = df.sort_values(key + ["filed", "accession"])
    instant = df.period_start.isna()
    by_key = df.groupby(key)["filed"]
    pick = by_key.transform("max").where(~instant, by_key.transform("min"))
    tied = df[df.filed == pick]
    conflicts = tied.groupby(key)["value"].nunique()
    conflicts = conflicts[conflicts > 1]
    if len(conflicts):
        print("\nCONFLICT: same key, same filing date, different values:")
        print(tied.set_index(key).loc[conflicts.index].to_string())
        sys.exit("Stopping: resolve conflicting values by hand.")
    kept = pd.concat([df[~instant].drop_duplicates(key, keep="last"),
                      df[instant].drop_duplicates(key, keep="first")]).sort_values(key)
    report_conflicts(df, kept, key)
    return kept.drop(columns="_start")


def report_conflicts(df, kept, key):
    print("\n=== Filing conflicts ===")
    n = df.groupby(key)["value"].nunique()
    n = n[n > 1]
    if not len(n):
        print("NONE")
        return
    kept_by_key = kept.set_index(key)
    for k in n.index:
        ticker, metric, concept, _, end = k
        grp = df.set_index(key).loc[[k]]
        r = kept_by_key.loc[k]
        start = "-" if pd.isna(r.period_start) else r.period_start.date()
        print(f"{ticker} {metric} {concept} {r.period_basis} {start} .. {end.date()}  "
              f"kept {r.value:,} ({r.accession})")
        for g in grp.itertuples():
            print(f"    {g.value:>20,}  {g.accession}  filed {g.filed.date()}")


def copy_tag_suspects(kept):
    """Kept rows whose value equals another kept row's value at a different period_end, same (ticker, metric), same accession."""
    m = kept.merge(kept, on=["ticker", "metric", "accession", "value"], suffixes=("", "_match"))
    m = m[m.period_end != m.period_end_match]
    return m[["ticker", "metric", "concept", "period_basis", "period_start", "period_end", "value",
              "accession", "filed", "concept_match", "period_basis_match", "period_start_match",
              "period_end_match"]].drop_duplicates()


def covered_periods(rows, metric):
    """Fiscal (year, quarter) pairs a concept covers, per FLOW_COVER or instant rows."""
    if rows.empty:
        return set()
    if metric in INSTANT_METRICS:
        ok = rows[rows.period_basis == "instant"]
    else:
        mask = pd.Series([b in FLOW_COVER[q] for b, q in zip(rows.period_basis, rows.fiscal_quarter)],
                         index=rows.index, dtype=bool)
        ok = rows[mask]
    return set(zip(ok.fiscal_year, ok.fiscal_quarter))


def fmt_periods(periods):
    return " ".join(f"FY{fy}Q{fq}" for fy, fq in sorted(periods)) or "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download raw JSON")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    download(args.refresh)

    allrows = pd.concat([load_rows(t) for t in TICKERS], ignore_index=True)

    # Every 'other' row, across all candidate concepts, before dedupe.
    other = allrows[allrows.period_basis == "other"].copy()
    print(f"\n=== Rows classified 'other' ({len(other)}) ===")
    if len(other):
        other["days"] = (other.period_end - other.period_start).dt.days
        print(other[["ticker", "metric", "concept", "period_start", "period_end", "days",
                     "value", "form", "accession", "filed"]].to_string(index=False))

    rows = dedupe(allrows[allrows.period_basis != "other"])

    print("\n=== Copy-tag suspects ===")
    sus = copy_tag_suspects(rows)
    if len(sus):
        with pd.option_context("display.width", 250):
            print(sus.to_string(index=False))
    else:
        print("NONE")

    # Coverage table and concept choice.
    print("\n=== Concept coverage (window periods; flows: Q1=Q, Q2=Q|YTD6, Q3=Q|YTD9, Q4=FY) ===")
    chosen, gaps, table = {}, [], []
    for t in TICKERS:
        need = {(fy, q) for fy in WINDOW[t] for q in range(1, 5)}
        for metric, (_, concepts) in CANDIDATES.items():
            for concept in concepts:
                sub = rows[(rows.ticker == t) & (rows.metric == metric) & (rows.concept == concept)]
                have = covered_periods(sub, metric) & need
                full = have == need
                if full and (t, metric) not in chosen:
                    chosen[(t, metric)] = concept
                table.append({"ticker": t, "metric": metric, "concept": concept,
                              "n": f"{len(have)}/{len(need)}",
                              "chosen": "<==" if chosen.get((t, metric)) == concept else "",
                              "covers": fmt_periods(have), "missing": fmt_periods(need - have)})
            if (t, metric) not in chosen:
                gaps.append((t, metric))
    with pd.option_context("display.max_colwidth", None, "display.width", 250):
        print(pd.DataFrame(table).to_string(index=False))

    # Both revenue concepts side by side at FY, so an unexpected concept choice is visible.
    rev = rows[(rows.metric == "revenue") & (rows.period_basis == "FY")]
    if len(rev):
        print("\n=== Revenue FY values by candidate concept (for the 'unexpected concept' check) ===")
        print(rev.pivot_table(index=["ticker", "fiscal_year"], columns="concept",
                              values="value", aggfunc="first").to_string())

    if gaps:
        print("\nGAPS: no single concept covers every window period for:")
        for t, m in gaps:
            print(f"  {t} {m}")
        sys.exit("Stopping per SPEC §6.2: decide the concept manually and record it. "
                 "No parquet written.")

    keep = pd.Series([chosen[(t, m)] == c for t, m, c in zip(rows.ticker, rows.metric, rows.concept)],
                     index=rows.index)
    out = rows[keep][COLUMNS].sort_values(["ticker", "metric", "period_end", "period_start"])
    out = out.reset_index(drop=True)
    assert out.groupby(["ticker", "metric"]).concept.nunique().eq(1).all()
    assert len(out.groupby(["ticker", "metric"])) == len(TICKERS) * len(CANDIDATES)
    for c in ["period_start", "period_end", "filed"]:
        out[c] = out[c].dt.date
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    print(f"\nwrote {len(out)} rows to {OUT_PATH}")

    manual_check(out)
    acceptance(out)


def show(df):
    for r in df.itertuples():
        print(f"  {r.ticker} {r.metric} {r.concept} = {r.value:,.0f} {r.unit}  "
              f"[{r.period_start} .. {r.period_end}, {r.period_basis}, FY{r.fiscal_year}Q{r.fiscal_quarter}]\n"
              f"    form {r.form}, accession {r.accession}, filed {r.filed}\n"
              f"    {filing_url(r.cik, r.accession)}")


def manual_check(out):
    print("\n=== For manual check ===")
    print("(a) CMG FY2025 revenue")
    a = out[(out.ticker == "CMG") & (out.metric == "revenue") & (out.period_basis == "FY")
            & (out.fiscal_year == 2025)]
    show(a)
    print("(b) DRI fiscal Q3 2025 operating cash flow, YTD9 row")
    b = out[(out.ticker == "DRI") & (out.metric == "op_cash_flow") & (out.period_basis == "YTD9")
            & (out.fiscal_year == 2025) & (out.fiscal_quarter == 3)]
    show(b)
    fy = out[(out.ticker == "DRI") & (out.period_basis == "FY") & (out.fiscal_year == 2026)]
    if len(fy):
        r = fy.iloc[0]
        days = (pd.Timestamp(r.period_end) - pd.Timestamp(r.period_start)).days + 1
        print(f"DRI FY2026 FY period {r.period_start} .. {r.period_end} = {days} days "
              f"({days // 7} weeks). Confirm on the 10-K cover page.")


def acceptance(out):
    print("\n=== Phase 1 acceptance checks ===")
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"\n{detail}" if detail else ""))

    cmg = out[(out.ticker == "CMG") & (out.metric == "revenue") & (out.period_basis == "FY")
              & (out.fiscal_year == 2025)]
    check("CMG FY2025 revenue printed", len(cmg) == 1,
          f"  {cmg.value.iloc[0]:,.0f} USD" if len(cmg) == 1 else f"  found {len(cmg)} rows")

    # DRI labels: each row's fiscal_year must equal the end year of the filed FY period that
    # contains its period_end. Uses the company's own FY dates, not fiscal_labels().
    dri = out[out.ticker == "DRI"]
    fys = dri[dri.period_basis == "FY"][["period_start", "period_end"]].drop_duplicates()
    bad, unmatched = [], []
    for r in dri.itertuples():
        hit = fys[(fys.period_start <= r.period_end) & (r.period_end <= fys.period_end)]
        if len(hit) == 0:
            unmatched.append(r)
        elif pd.Timestamp(hit.period_end.iloc[0]).year != r.fiscal_year:
            bad.append(r)
    q = dri[dri.period_basis != "instant"].groupby(["fiscal_year", "fiscal_quarter", "period_basis"]) \
        .period_end.agg(["min", "max"]).reset_index()
    check("DRI quarters labeled with the right fiscal years", not bad and not unmatched,
          q.to_string(index=False) + (f"\n  mislabeled: {len(bad)}, outside filed FY: {len(unmatched)}"
                                      if bad or unmatched else ""))

    ocf = out[out.metric == "op_cash_flow"]
    missing = []
    for t in TICKERS:
        for fy in WINDOW[t]:
            for basis, fq in [("YTD6", 2), ("YTD9", 3)]:
                n = len(ocf[(ocf.ticker == t) & (ocf.fiscal_year == fy) & (ocf.fiscal_quarter == fq)
                            & (ocf.period_basis == basis)])
                if n != 1:
                    missing.append(f"  {t} FY{fy}Q{fq} {basis}: {n} rows")
    check("Q2 and Q3 operating cash flow present as YTD6 and YTD9 rows", not missing, "\n".join(missing))

    check("No 'other' period types in output", (out.period_basis == "other").sum() == 0)

    per = out.groupby(["ticker", "metric"]).concept.nunique()
    check("One concept per (ticker, metric), no gaps",
          per.eq(1).all() and len(per) == len(TICKERS) * len(CANDIDATES))

    print(f"\n{sum(results)}/{len(results)} checks passed")
    if not all(results):
        sys.exit(1)


if __name__ == "__main__":
    main()
