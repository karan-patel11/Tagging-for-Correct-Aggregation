import pandas as pd

from ingest_sec import covered_periods


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
