# Tagging for Correct Aggregation

A small experiment comparing restaurant-sector answers from an AI agent given raw schemas, prose descriptions, structured tags, or semantic tools.

**Status:** the evaluation is complete; the static results page is under review. Open [docs/index.html](docs/index.html) locally to explore recorded runs. See the [results summary](eval/results/summary.md) and [error analysis](docs/error_analysis.md). No model calls are made by the page.

Companies: CMG, WING, YUM, DRI. Sources: SEC XBRL filings, BLS, Census, Wikipedia pageviews, earnings releases.

## Question provenance

Question wording drafted on 2026-10-24, frozen on 2026-10-27. The first populated draft is commit `f4f35b4`; the lightweight `questions-frozen` tag points to commit `88506ef`, dated 2026-10-27. A lightweight tag has no separate creation timestamp, so the freeze date is taken from its target commit. Both dates agree in UTC and America/New_York.

Four replacement questions (q039–q042) were added in commit `4f06c42` on 2026-10-27 UTC (2026-10-26 Eastern), after the core logic existed. Several method hints were also removed then. The original draft predates the core logic; the final question set does not. All questions were frozen before the pilot and full evaluation.

The full evaluation's recorded start times are 2026-10-28 00:17:40–00:25:49 UTC, equivalent to 2026-10-27 20:17:40–20:25:49 America/New_York. These are run start times, not completion times. The page labels its run date as UTC.

## Limitations

- Financial coverage is fiscal 2024–2025 for CMG, WING and YUM, with Darden's fiscal 2025–2026. Fiscal labels do not imply aligned calendar periods.
- The sample contains 42 questions, seven per category, four companies and one model. It does not establish that either context format is better.
- The author wrote both the questions and the system. Freezing prevents later edits but does not remove selection bias.
- Setup D changes both the interface and enforcement. Its tool coverage closely follows the question categories; the replay includes its failures and available recovery routes.
- Wikipedia pageviews are a proxy for alternative data. Habit combines two article titles, including traffic to its former title; other brands do not include redirect views.
- No amended 10-K or 10-Q filings are included.
- Results use the corrected scorer. Its unit-parsing bug changed 12 B/C run scores; the disclosure and before/after counts remain in the summary and page.

## Quickstart

```bash
pip install -e ".[dev]"
cp .env.example .env   # add your API key
python src/build_db.py && pytest && python eval/run_eval.py --pilot
```

See [SPEC.md](SPEC.md) for the full design.

## Run the MCP server

The server (`src/mcp_server.py`) exposes four tools over stdio: `list_metrics`, `describe_column`, `get_metric`, `aggregate`. It reads `data/warehouse.duckdb` read-only, so build the database first (`python src/build_db.py`).

```bash
claude mcp add restaurant-semantics -- python /absolute/path/to/Tagging-for-Correct-Aggregation/src/mcp_server.py
```

Use the Python that has the project installed (a venv's `python` needs its absolute path too). Then ask Claude Code: "What was Darden's operating cash flow in fiscal Q3 2025, and where does that number come from?"
