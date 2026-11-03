# Valid SQL, Wrong Answer

**Does tagging data help an AI agent aggregate financial numbers correctly?** A small, reproducible experiment on restaurant-sector SEC filings, government macro data and vendor-style alternative data.

**Results page (start here):** https://karan-patel11.github.io/Tagging-for-Correct-Aggregation/

<!-- Add the Loom link here once it is final: **Two-minute video:** <link> -->

---

## The short version

| Setup | What the model gets | Accuracy (mean) | Lowest–highest run | Stored-trap hits |
|---|---|---|---|---|
| A · Schema only | Table and column names, `run_sql` | 96.8% | 92.9–100.0% | 1 of 153 |
| B · Prose | Plain-English facts about every metric, `run_sql` | 100.0% | 100.0–100.0% | 0 of 153 |
| C · Structured tags | The same facts as YAML tags, `run_sql` | 98.4% | 97.6–100.0% | 0 of 153 |
| D · Enforcing tools | No SQL; 4 tools that read and enforce the tags | 98.4% | 95.2–100.0% | 0 of 153 |

42 questions × 3 runs × 4 setups = 504 runs, `claude-haiku-5-5`, run on 2026-10-28 (UTC). Total cost: **$0.43**.

**What it shows:**

1. **Accuracy was not the bottleneck.** With no tags at all, the model was already 96.8% correct (8 wrong runs out of 504 across all setups). This test can't show tags improving accuracy, and I don't claim it does.
2. **Format didn't matter.** Prose and structured tags carrying the same facts disagreed on 1 of 42 questions: too few to separate from noise.
3. **What did change was traceability and false alarms.** Only the enforcing tools returned a filing link with every answer (114 of 114 answered runs, against none when the model wrote SQL). Unneeded caveats fell from 34 of 102 runs with no tags to 9 with prose and 7 with the tools (an unplanned measure, so a lead, not a result).

---

## Why this project exists

Analysts increasingly ask AI assistants questions about financial data in plain English, and most of them can't check the SQL the model writes. So trust has to come from the system being correct and transparent.

Connecting a model to a database (for example through an MCP server) is the easy part. The hard part is making a dataset **AI-accessible end to end**: the model has to know what each column *means* and how it may be combined. A query can run without error and still return the wrong number:

> *"What were Yum's total assets for 2025?"*
> Wrong: `SUM(total_assets)` over four quarters (counts the same balance four times).
> Right: the balance at the last quarter-end, **$8,197,000,000** ([10-K](https://www.sec.gov/Archives/edgar/data/1041061/000104106126000084/)).

The schema doesn't say which is correct. Data warehousing has names for this (Kimball's additive, semi-additive and non-additive measures), and semantic layers already enforce it for metrics someone has defined. The question this project asks is narrower and practical:

> **How much of that error does each layer of context and enforcement actually remove, and does the *format* of the context matter?**

That is the decision a data team faces when it starts tagging its catalog: write column descriptions, write structured tags, or put the rules in a tool the model can't bypass.

## The seven traps

Each trap is a rule the schema doesn't state, taken from real filings and public data.

| Trap | The rule | Example in this data |
|---|---|---|
| Time additivity | Balances are read at period end, never summed | Yum's FY2025 total assets |
| Ratios | Combined margin = total income ÷ total revenue, not the mean of margins | CMG + YUM + DRI operating margin |
| YTD basis | 10-Q cash flows are year-to-date; a quarter is the difference of two | Darden fiscal Q3 operating cash flow = YTD9 − YTD6 |
| Fiscal calendar | Darden's year ends in May; its quarters don't match calendar quarters | Darden fiscal Q4 2026 = FY − YTD9 = $3,718,800,000 |
| Indices | CPI levels can't be summed; use % change or a period average | CPI food away from home, Dec-to-Dec |
| Hierarchy | Brand rows roll up to the parent; the parent's own row isn't added on top | KFC's share of Yum's brand pageviews |
| Comparability | Each company defines comparable sales differently; missing data needs a refusal | Chipotle vs. Wingstop comps; CAVA comps (not in the data) |

## Approach

**Data (4 companies: Chipotle, Wingstop, Yum! Brands, Darden; fiscal 2024–2025, Darden fiscal 2025–2026):**

- SEC XBRL fundamentals, stored **as filed** (single quarters, YTD6, YTD9, full year, balances). The traps are kept on purpose; cleaning them away would make the test meaningless.
- Comparable sales and their definitions, entered by hand from 8-K earnings releases and 10-Ks.
- CPI (BLS) and food-service sales (Census), downloaded from the primary agencies.
- Wikipedia pageviews for brands and parent companies, as a public stand-in for an alternative-data panel (brand vs. parent grain, renamed series). Used only to test aggregation, not to predict anything.

**Tags (`tags/tags.yaml`):** one tag per *metric*, not per column, because `fundamentals` is a long table where one `value` column holds many metrics. Each tag states semantic type, additivity over time and entities, time rollup, valid aggregation methods, period basis, calendar, units and lineage, and is validated with Pydantic.

**Core logic (`semantics.py`):** the only place aggregation rules live. It reads the tags, derives single quarters from YTD values (checking that periods are contiguous), rejects disallowed methods with a `use_instead` suggestion, warns on mixed fiscal calendars and cross-company comps, and attaches a source link to every value.

**MCP server:** four thin tools over `semantics.py` (`list_metrics`, `describe_column`, `get_metric`, `aggregate`). The evaluation's setup D uses the same functions and the same tool descriptions, so what is demoed is what was measured.

```
SEC XBRL · Wikimedia · BLS/Census · earnings releases
        → ingestion → DuckDB (stored as filed)
        → tags.yaml (validated) → semantics.py
        → MCP server (demo)  +  eval harness (504 runs)
        → score.py → summary.json → static results page
```

**The four setups** each add one thing: A (schema) → B (facts as prose) → C (same facts as structured tags) → D (tags enforced by tools, no SQL). B and C contain identical facts, so B vs. C isolates format. D changes the interface and the enforcement together, so its result can't separate the two.

## How the answers were checked

- The answer key is computed by `eval/make_questions.py` with direct SQL, **independent of `semantics.py`**, so the code under test doesn't grade itself.
- 42 of 42 questions verified (134 rows in `eval/verification_log.csv`). Of 96 distinct inputs, 92 were checked against primary sources (23 by hand, all 92 by an AI-assisted read), with 0 mismatches; the other 4 record that the data doesn't exist.
- Questions were drafted on 2026-10-24, before `semantics.py` was first committed; four replacements were added on 2026-10-27. All were frozen with `git tag questions-frozen` before the first run on 2026-10-28.
- Scoring stores each trap's answer, so a wrong run is labeled with *which* mistake it made.
- One post-hoc scorer fix, disclosed: a unit-parsing bug read `USD_millions` as unscaled. Fixing it changed 12 runs (B 8, C 4) from incorrect to correct. The scoring rule itself didn't change.
- 239 tests pass.

## Where it failed

All 8 wrong runs, by cause (details in [`docs/error_analysis.md`](docs/error_analysis.md)):

- **4 missed a calendar warning** (q010, A and C): combined Darden's May year with December year-ends without flagging it.
- **1 answered the full year instead of the requested quarter** (q017, A): the only stored-trap hit in 612 checks.
- **1 arithmetic slip after correct retrieval** (q031, A).
- **2 failures of the enforcing tools' own interface** (q030, q034, D): a period format the tool rejected, and a supported comps route the model didn't discover. The tool became the weak point.

## Follow-up experiments (added after the main results)

- **Why was the baseline so strong?** Setup A rerun on a copy of the database with the meaning-carrying columns removed (`period_basis`, `fiscal_quarter`, `grain`, etc.). No detectable difference (1 discordant question). Every removed column could be recomputed from columns that stayed, so this data simply wasn't hard enough to separate the setups.
- **Can a model write the tags?** With model-drafted tags in place of human ones, setup D's correct runs fell from 124 to 62 of 126. It failed safely (refusals and unfinished answers, no confidently wrong numbers), but 10 of 13 tag fields needed human correction. The approach this points to: the model drafts, a person approves, a benchmark checks.

## What this means in practice

For making existing datasets AI-accessible, the work that paid off here was not a smarter model or a particular description format. It was: descriptions a person has checked, a tool that returns the source with every number, and a fixed set of real analyst questions to measure before and after any change.

## Limitations

- Small sample: 7 questions per category, 4 companies, one model, a two-year window.
- I wrote both the questions and the system. Mitigation: questions drafted before the core logic and frozen before any run.
- D's tools were designed around these question categories, so its advantage on answerable questions is partly by design.
- Pageviews are only a proxy for vendor data. No filing amendments are included.
- The engine was hardened after the study (`followup/engine_fix/REPLAY.md`); the recorded runs predate that change and were not re-run.

## Related approaches

Kimball's additive, semi-additive and non-additive measures; dbt MetricFlow's `non_additive_dimension`; Databricks metric views. `semantics.py` is a minimal semantic layer. The contribution here is the measurement, not the idea.

**How this maps to a data catalog:** tags correspond to column comments and tags in a catalog such as Unity Catalog; the enforcing `aggregate` tool plays the role of metric views or trusted queries; the question set works like a benchmark set.

## Next steps

1. A harder benchmark: data whose meaning can't be recovered from other columns, more questions, and grading of the explanation as well as the number.
2. Vendor onboarding: model-drafted tags, human approval, benchmark-gated.
3. Freshness fields in the tags for streaming sources.

## Reproduce

```bash
pip install -e .
python src/build_db.py && pytest && python eval/run_eval.py --pilot
```

The full run needs `ANTHROPIC_API_KEY` in `.env` (never committed) and cost $0.43. Raw downloads are committed under `data/raw/` with retrieval dates, so the database rebuilds without network access to SEC or Wikimedia.

## Repository map

| Path | What it is |
|---|---|
| `src/ingest_*.py`, `src/build_db.py` | Ingestion and DuckDB build |
| `tags/tags.yaml`, `src/tags.py` | Tags and their validator |
| `src/semantics.py` | The only place aggregation rules live |
| `src/mcp_server.py`, `src/tool_specs.py` | MCP server and shared tool descriptions |
| `eval/` | Questions, answer key, verification logs, harness, scorer, results |
| `docs/error_analysis.md` | Error analysis |
| `docs/index.html`, `report/` | Static results page and its generator |

---

*A small experiment, not a production system. Every number above comes from the recorded runs on 2026-10-28 (UTC) and the exploratory runs on 2026-11-01 (UTC), as published on the [results page](https://karan-patel11.github.io/Tagging-for-Correct-Aggregation/).*
