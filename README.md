# Tagging for Correct Aggregation

A small experiment: how often does an AI agent get restaurant-sector calculations wrong when it only sees raw tables, and how much do structured column tags, plus an MCP tool that enforces them, fix it?

**Status:** work in progress. Results, video and write-up will appear here.

Companies: CMG, WING, YUM, DRI. Sources: SEC XBRL filings, FRED, Wikipedia pageviews, earnings releases.

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
