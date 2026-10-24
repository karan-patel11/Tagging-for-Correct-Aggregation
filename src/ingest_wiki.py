"""Phase 2: Wikipedia pageviews ingestion (SPEC.md §6.3).

Reads the article titles from data/raw/wiki/titles.csv, downloads daily user pageviews
for each title (one request at a time) into data/raw/wiki/{api_title}.json, and writes
one row per (date, article_title) to data/interim/brand_attention_daily.parquet.
Nothing is summed, filled or imputed. Then runs the Phase 2 checks W1-W5.

Run: python src/ingest_wiki.py [--refresh]
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "wiki"
TITLES_PATH = RAW_DIR / "titles.csv"
RETRIEVED_PATH = RAW_DIR / "retrieved.json"
OUT_PATH = ROOT / "data" / "interim" / "brand_attention_daily.parquet"

ENDPOINT = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            "en.wikipedia/all-access/user/{title}/daily/20240101/20251231")
START, END = pd.Timestamp("2024-01-01"), pd.Timestamp("2025-12-31")
N_DAYS = (END - START).days + 1  # 731: 2024 is a leap year

COLUMNS = ["date", "article_title", "brand", "grain", "parent_ticker", "views"]

RETRY_WAITS = [5, 15, 45, 90]  # seconds before each 429 retry when there is no Retry-After
TITLE_PAUSE = 2                # seconds between titles


# ---------- download ----------

def user_agent():
    load_dotenv(ROOT / ".env")
    ua = os.environ.get("WIKI_USER_AGENT", "").strip().strip('"')
    if not ua:
        sys.exit("WIKI_USER_AGENT is not set (SPEC.md §6.3).")
    return ua


def retry_after(r):
    """Seconds from a Retry-After header (delta-seconds or HTTP-date), or None if absent/unreadable."""
    v = r.headers.get("Retry-After")
    if v is None:
        return None
    try:
        return max(0, int(v.strip()))
    except ValueError:
        try:
            return max(0, (parsedate_to_datetime(v) - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError):
            return None


def fetch(t, url, ua):
    """GET one title. Retries only on 429, at most len(RETRY_WAITS) times; any status other
    than 200/404/429 stops at once."""
    for attempt in range(len(RETRY_WAITS) + 1):
        r = requests.get(url, headers={"User-Agent": ua}, timeout=60)
        if r.status_code in (200, 404):
            return r
        if r.status_code != 429:
            sys.exit(f"HTTP {r.status_code} for {t}: {url}\n{r.text[:500]}\nStopping.")
        if attempt == len(RETRY_WAITS):
            sys.exit(f"HTTP 429 for {t} after {len(RETRY_WAITS)} retries: {url}\n{r.text[:500]}\nStopping.")
        server = retry_after(r)
        wait = server if server is not None else RETRY_WAITS[attempt]
        print(f"429 for {t}: retry {attempt + 1}/{len(RETRY_WAITS)} in {wait:g}s "
              f"({'Retry-After' if server is not None else 'backoff schedule'})", flush=True)
        time.sleep(wait)


def download(titles, refresh):
    """One request at a time. 404 = no data for that title; 429 is retried; any other error stops.
    A title is skipped when its raw JSON exists and retrieved.json has its entry.
    retrieved.json is rewritten after every title, so partial progress is recorded."""
    retrieved = json.loads(RETRIEVED_PATH.read_text()) if RETRIEVED_PATH.exists() else {}
    missing = [t for t in titles.api_title
               if refresh or t not in retrieved or not (RAW_DIR / f"{t}.json").exists()]
    if not missing:
        return retrieved
    ua = user_agent()
    for i, t in enumerate(missing):
        if i:
            time.sleep(TITLE_PAUSE)
        url = ENDPOINT.format(title=quote(t, safe=""))
        r = fetch(t, url, ua)
        if r.status_code == 404:
            print(f"404 (no data): {t}  {url}")
        (RAW_DIR / f"{t}.json").write_text(r.text)
        items = len(r.json().get("items", [])) if r.status_code == 200 else 0
        retrieved[t] = {"title": t, "url": url, "http_status": r.status_code, "items": items,
                        "retrieved_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        RETRIEVED_PATH.write_text(json.dumps(retrieved, indent=2) + "\n")
        print(f"downloaded {t}: HTTP {r.status_code}, {items} items", flush=True)
    return retrieved


# ---------- parse ----------

def load_rows(title, retrieved):
    """The title's daily items as stored rows. A logged 404 gives 0 rows."""
    if retrieved[title]["http_status"] == 404:
        return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"),
                             "article_title": pd.Series(dtype=str), "views": pd.Series(dtype="int64")})
    items = json.loads((RAW_DIR / f"{title}.json").read_text())["items"]
    for it in items:
        if it["article"] != title or it["granularity"] != "daily" or it["agent"] != "user" \
                or it["access"] != "all-access" or it["project"] != "en.wikipedia":
            sys.exit(f"Unexpected item for {title}: {it}")
    return pd.DataFrame({"date": pd.to_datetime([it["timestamp"][:8] for it in items], format="%Y%m%d"),
                         "article_title": title,
                         "views": [int(it["views"]) for it in items]})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download raw JSON")
    args = ap.parse_args()

    titles = pd.read_csv(TITLES_PATH, dtype=str)
    retrieved = download(titles, args.refresh)

    rows = pd.concat([load_rows(t, retrieved) for t in titles.api_title], ignore_index=True)
    out = rows.merge(titles.rename(columns={"api_title": "article_title"}), on="article_title")
    out = out[COLUMNS].sort_values(["article_title", "date"]).reset_index(drop=True)
    out["views"] = out["views"].astype("int64")
    out["date"] = out["date"].dt.date
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT_PATH, index=False)
    print(f"\nwrote {len(out)} rows to {OUT_PATH}")

    checks(out, titles, retrieved)


# ---------- checks ----------

def checks(out, titles, retrieved):
    df = out.copy()
    df["date"] = pd.to_datetime(df["date"])
    calendar = pd.date_range(START, END, freq="D")
    results = {}

    def verdict(name, ok, rule):
        results[name] = ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}  ({rule})")

    print("\n=== W1. Rows per api_title, first and last date ===")
    w1 = []
    for t in titles.api_title:
        sub = df[df.article_title == t]
        w1.append({"api_title": t, "http_status": retrieved[t]["http_status"], "rows": len(sub),
                   "first": sub.date.min().date() if len(sub) else "-",
                   "last": sub.date.max().date() if len(sub) else "-"})
    print(pd.DataFrame(w1).to_string(index=False))
    in_window = df.date.between(START, END).all()
    fetched = all(retrieved[t]["http_status"] in (200, 404) for t in titles.api_title)
    verdict("W1", in_window and fetched,
            "every title fetched with HTTP 200 or a logged 404; every date in 2024-01-01..2025-12-31")

    print("\n=== W2. Distinct dates per brand, summed across its titles (must be 731) ===")
    by_brand = df.groupby(["brand", "date"]).views.sum().reset_index()
    w2 = by_brand.groupby("brand").date.agg(["nunique", "min", "max"])
    w2 = w2.reindex(titles.brand.unique())
    print(w2.rename(columns={"nunique": "distinct_dates", "min": "first", "max": "last"}).to_string())
    verdict("W2", w2["nunique"].eq(N_DAYS).all(), f"every brand has exactly {N_DAYS} distinct dates")

    print("\n-- Habit Burger Grill titles --")
    habit = df[df.brand == "Habit Burger Grill"]
    for t in titles[titles.brand == "Habit Burger Grill"].api_title:
        sub = habit[(habit.article_title == t) & (habit.views > 0)]
        first = sub.date.min().date() if len(sub) else "-"
        last = sub.date.max().date() if len(sub) else "-"
        print(f"  {t}: first date with views > 0 {first}, last {last}, days with views > 0: {len(sub)}")
    both = habit[habit.views > 0].groupby("date").article_title.nunique()
    both = both[both == 2]
    if len(both):
        print(f"  days where both titles have views > 0: {len(both)} "
              f"({both.index.min().date()} .. {both.index.max().date()})")
    else:
        print("  days where both titles have views > 0: 0")

    print("\n=== W3. Dates with zero total views per brand (must be none) ===")
    w3 = []
    for b in titles.brand.unique():
        s = by_brand[by_brand.brand == b].set_index("date").views.reindex(calendar, fill_value=0)
        zero = s[s == 0]
        w3.append({"brand": b, "zero_view_dates": len(zero),
                   "dates": ", ".join(str(d.date()) for d in zero.index[:10]) + (" ..." if len(zero) > 10 else "")})
    print(pd.DataFrame(w3).to_string(index=False))
    verdict("W3", all(r["zero_view_dates"] == 0 for r in w3),
            "no calendar date with zero total views; a date with no rows counts as zero here")

    print("\n=== W4. Duplicate (date, article_title) keys (must be none) ===")
    dup = df[df.duplicated(["date", "article_title"], keep=False)]
    print(dup.to_string(index=False) if len(dup) else "NONE")
    verdict("W4", dup.empty, "no duplicate (date, article_title)")

    print("\n=== W5. Total views per api_title, 2024 and 2025 ===")
    df["year"] = df.date.dt.year
    w5 = df.pivot_table(index="article_title", columns="year", values="views", aggfunc="sum", fill_value=0)
    w5 = w5.reindex(titles.api_title, fill_value=0)
    print(w5.map(lambda v: f"{v:,}").to_string())
    verdict("W5", set(df.year.unique()) <= {2024, 2025},
            "informational; every row falls in 2024 or 2025, so the two totals cover all rows")

    print(f"\n{sum(results.values())}/{len(results)} checks passed")
    if not all(results[k] for k in ("W2", "W3", "W4")):
        sys.exit("W2, W3 or W4 failed. Stopping.")
    if not all(results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
