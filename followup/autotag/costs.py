"""Prices, the follow-up's cost cap, and the ledger of what has already been spent.

The cap covers the whole follow-up (PREREG "Cost stop"): the one-id cost check, 3 drafts x 43 ids
and 126 setup D runs. Spend so far is read back from the files those steps write, so it holds
across processes and resumed sessions.
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent

COST_CAP_USD = 3.75  # raised from 3.00 before any drafting; see PREREG_DEVIATIONS.md

TAGGER_MODEL = "claude-sonnet-5-5"
# USD per million tokens for claude-sonnet-5-5, read from PRICING_URL on 2026-10-29 (model pricing
# table): base input $2, 5m cache writes $2.50, cache hits and refreshes $0.10 (footnote: 0.05x base
# input on Sonnet 5.5), output $10. The page lists no prompt-length tier for Sonnet 5.5. Only the
# 5-minute cache TTL is used.
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICES_READ_ON = "2026-10-29"
TAGGER_PRICES = {"input": 2.00, "cache_write_5m": 2.50, "cache_read": 0.10, "output": 10.00}
# Minimum cacheable prompt length for Claude Sonnet 5.5 (and Haiku 5.5), read from the prompt
# caching docs' "Cache limitations" on 2026-10-29.
CACHING_URL = "https://platform.claude.com/docs/en/build-with-claude/prompt-caching"
TAGGER_MIN_CACHEABLE_TOKENS = 512

COST_CHECK = HERE / "results" / "cost_check.json"
DRAFTS = HERE / "drafts"
D_AUTOTAG = HERE / "results" / "D_autotag.jsonl"


def tagger_cost(usage):
    p = TAGGER_PRICES
    return (usage.get("input_tokens", 0) * p["input"]
            + usage.get("cache_creation_input_tokens", 0) * p["cache_write_5m"]
            + usage.get("cache_read_input_tokens", 0) * p["cache_read"]
            + usage.get("output_tokens", 0) * p["output"]) / 1e6


def spent_so_far():
    """USD already billed in this follow-up, from the files each step writes."""
    total = 0.0
    if COST_CHECK.exists():
        total += json.loads(COST_CHECK.read_text())["sample_call"]["cost_usd"]
    for raw in sorted(DRAFTS.glob("raw/draft_*/*.json")):
        total += json.loads(raw.read_text()).get("cost_usd", 0.0)
    if D_AUTOTAG.exists():
        for line in D_AUTOTAG.read_text().splitlines():
            if line.strip():
                try:
                    total += json.loads(line).get("cost_usd", 0.0)
                except json.JSONDecodeError:
                    pass
    return total
