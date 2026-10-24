import pandas as pd

from ingest_sec import covered_periods, dedupe


def test_covered_periods_empty_returns_empty_set():
    rows = pd.DataFrame(columns=["period_basis", "fiscal_year", "fiscal_quarter"])
    assert covered_periods(rows, "op_cash_flow") == set()


def test_covered_periods_two_rows():
    rows = pd.DataFrame({
        "period_basis": ["Q", "YTD6"],
        "fiscal_year": [2025, 2025],
        "fiscal_quarter": [1, 2],
    })
    assert covered_periods(rows, "op_cash_flow") == {(2025, 1), (2025, 2)}


def _filings(start, values, filed):
    return pd.DataFrame({
        "ticker": "DRI", "metric": "total_assets" if start is None else "net_income",
        "concept": "Assets" if start is None else "NetIncomeLoss",
        "period_start": pd.to_datetime([start] * len(values)),
        "period_end": pd.to_datetime(["2024-08-25"] * len(values)),
        "period_basis": "instant" if start is None else "Q",
        "value": values, "accession": [f"acc-{i}" for i in range(len(values))],
        "filed": pd.to_datetime(filed),
    })


def test_dedupe_instant_keeps_earliest_filed():
    df = _filings(None, [100.0, 200.0], ["2024-09-27", "2025-09-26"])
    out = dedupe(df)
    assert len(out) == 1 and out.value.iloc[0] == 100.0


def test_dedupe_duration_keeps_latest_filed():
    df = _filings("2024-05-27", [100.0, 200.0], ["2024-09-27", "2025-09-26"])
    out = dedupe(df)
    assert len(out) == 1 and out.value.iloc[0] == 200.0
