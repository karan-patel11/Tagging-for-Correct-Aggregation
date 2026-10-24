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
