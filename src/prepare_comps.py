"""Phase 4: shape the hand-entered comps into the SPEC.md §7 comps_quarterly schema.

Reads data/raw/comps_entered.csv (local file only, no network) and writes
data/comps_quarterly.csv with the columns ticker, fiscal_year, fiscal_quarter,
comp_sales_pct, definition_id, source_url. Every value is read and written as a string, so
"-4.0" stays "-4.0"; nothing is parsed, rounded or filled. comp_sales_pct is copied from
comps_pct and source_url is copied unchanged. definition_id is looked up from the ticker; any
other ticker is an error. period_end, metric and notes stay in the raw file as provenance.

Run: python src/prepare_comps.py
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_PATH = ROOT / "data" / "raw" / "comps_entered.csv"
OUT_PATH = ROOT / "data" / "comps_quarterly.csv"

DEFINITION_ID = {"CMG": "CMG_10K", "WING": "WING_10K", "DRI": "DRI_10K"}
OUT_COLUMNS = [
    "ticker",
    "fiscal_year",
    "fiscal_quarter",
    "comp_sales_pct",
    "definition_id",
    "source_url",
]


def main() -> int:
    with open(RAW_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    out_rows = []
    for row in rows:
        ticker = row["ticker"]
        if ticker not in DEFINITION_ID:
            print(f"ERROR: unknown ticker {ticker!r} in {RAW_PATH.name}", file=sys.stderr)
            return 1
        out_rows.append(
            {
                "ticker": ticker,
                "fiscal_year": row["fiscal_year"],
                "fiscal_quarter": row["fiscal_quarter"],
                "comp_sales_pct": row["comps_pct"],
                "definition_id": DEFINITION_ID[ticker],
                "source_url": row["source_url"],
            }
        )

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"Wrote {len(out_rows)} rows to {OUT_PATH.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
