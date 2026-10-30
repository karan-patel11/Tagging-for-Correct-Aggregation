# Tagging for Correct Aggregation

**AI can calculate a financial number correctly and still answer the wrong question.** Asked for Darden's revenue in fiscal Q4 2026, an AI tool can return the full-year figure ($13,210,900,000) without any error. The right answer is $3,718,800,000: the full year minus the first nine months. An analyst who cannot read the query cannot catch it.

**The idea.** Attach rules ("tags") to every metric: whether it can be added up over time, which fiscal calendar it uses, which rows are parent totals.

1. **Measure: do the rules help?** One model (claude-haiku-5-5) answered 42 questions in four setups, 504 answers in total: only the database layout; a written description; a rules file; tools that enforce the rules. All four scored 97%–100%, too close to rank on this sample.
2. **Auto-tag: can an AI write the rules?** A stronger model (claude-sonnet-5-5) drafted them from column names, sample rows and the vendor's documentation ([pre-registered](followup/autotag/PREREG.md)). With its rules, correct answers fell from 124 to 62 of 126, through refusals or no final answer, not wrong numbers. The 64 misses: 20 rule errors by the AI; 21 source links missing from my inputs; 21 a missing parent/brand rule plus a crash in my engine; 2 unrelated.
3. **Harden: the engine trusted the rules blindly.** It now refuses what it cannot compute. Crashes 171 → 0; results for a calculation the hand-written rules forbid 5 → 1; 455 of 455 recorded tool calls behind the main results give identical output. New automatic checks catch 33 of 63 AI rule errors (derived from the same drafts, not tested on new data).

**What this suggests for a research data team** (suggested by this evidence, not proven): let AI draft the rules, but have a person sign off on how numbers combine; add automatic checks for rule combinations that cannot both be true; make the engine refuse anything it does not implement.

**Read the full story and every number's source on the [results page](https://karan-patel11.github.io/Tagging-for-Correct-Aggregation/)** ([docs/index.html](docs/index.html)).

## Detailed results

SQL that runs without error can still answer the wrong question about financial data, for example by summing four quarter-end balances into a meaningless "annual" total assets. This small experiment asks one model (claude-haiku-5-5) the same 42 restaurant-sector questions in four setups (A: table schema only; B: prose descriptions; C: a tags file; D: semantic tools, no SQL) and scores 504 recorded runs against an answer key computed with direct SQL and checked against the filings and agency data (25 of 134 source rows read by hand; see the results page).

**Main results** (from [eval/results/summary.md](eval/results/summary.md)):

- Accuracy was close across setups: A 96.8%, B 100.0%, C 98.4%, D 98.4% of 126 runs each. The sample is too small to rank them.
- One stored-trap hit in 504 runs (A, q017 run 2).
- Runs that set warning=true on questions whose answer key expects no caveat: A 34, B 9, C 19, D 7 of 102 each. Most cite stored filing dates or retrieval metadata (keyword match plus 4 manual corrections, listed in the JSON: [report/over_warning_reasons.json](report/over_warning_reasons.json)); they are not scored as errors, and the metric does not show that any setup hedges more or less well.

**Links:** [results page (docs/index.html)](docs/index.html) · [live page](https://karan-patel11.github.io/Tagging-for-Correct-Aggregation/) · video: TODO: video link · [results summary](eval/results/summary.md) · [error analysis](docs/error_analysis.md) · [terms and question texts](docs/key.md)

Question IDs: q017 means question 17 in [eval/questions.yaml](eval/questions.yaml); [docs/key.md](docs/key.md) lists the text of every ID mentioned here and in the error analysis. q017 is "What was Darden's total revenue in fiscal Q4 2026 (the 14-week quarter ended May 31, 2026), in US dollars?"

Companies: CMG, WING, YUM, DRI. Sources: SEC XBRL filings, BLS, Census, Wikipedia pageviews, earnings releases. No model calls are made by the results page.

## Limitations

- Financial coverage is fiscal 2024–2025 for CMG, WING and YUM, with Darden's fiscal 2025–2026. Fiscal labels do not imply aligned calendar periods.
- The sample contains 42 questions, seven per category, four companies and one model. It does not establish that either context format is better.
- The author wrote both the questions and the system. Freezing prevents later edits but does not remove selection bias.
- Setup D changes both the interface and enforcement. Its tool coverage closely follows the question categories; the replay includes its failures and available recovery routes.
- Wikipedia pageviews are a proxy for alternative data. Habit combines two article titles, including traffic to its former title; other brands do not include redirect views.
- No amended 10-K or 10-Q filings are included.
- Results use the corrected scorer. Its unit-parsing bug changed 12 B/C run scores; the disclosure and before/after counts remain in the summary and page. The affected spelling, `USD_millions`, appeared in FINAL only in B (eight runs) and C (four runs), all on Census questions q022–q024; both Census contexts specify that exact unit. The correction applies equally to all four setups. This wording match does not establish why the model chose that spelling.

## Disclosures

- Setup B's prose is generated from the tags by fixed sentence templates, one sentence per fact (`eval/make_contexts.py`). 51 of its 378 facts mirror a tag value verbatim (lineage `id_column`, `id_columns`, `concept_column`, and `time_rollup: none`), as listed in the script's output.
- The ratios category does not follow SPEC §11.2: it has 6 combined-margin questions (q007–q009, q011, q040, q041) plus q010, and none that sum one company's quarters into an annual margin (those drafts were dropped by the 2x-tolerance rule).
- D's q030 run 1 ended on the output-token limit (`max_tokens`) with no FINAL line; the transcript shows no text for the output tokens spent. It is scored incorrect.
- The error analysis was prepared with coding assistance.
- One model and a small sample: 42 questions, 3 runs per question per setup. The results describe these runs, not models or formats in general.

## Next steps

- Replace the static API key with workload identity federation if the evaluation is run in CI.

## Question provenance

Question wording drafted on 2026-10-24, frozen on 2026-10-27. The first populated draft is commit `f4f35b4`; the lightweight `questions-frozen` tag points to commit `88506ef`, dated 2026-10-27. A lightweight tag has no separate creation timestamp, so the freeze date is taken from its target commit. Both dates agree in UTC and America/New_York.

Four replacement questions (q039–q042) were added in commit `4f06c42` on 2026-10-27 UTC (2026-10-26 Eastern), after the core logic existed. Several method hints were also removed then. The original draft predates the core logic; the final question set does not. All questions were frozen before the pilot and full evaluation.

The full evaluation's recorded start times are 2026-10-28 00:17:40–00:25:49 UTC, equivalent to 2026-10-27 20:17:40–20:25:49 America/New_York. These are run start times, not completion times. The page labels its run date as UTC.

## Engine hardening (after the study)

After the auto-tag follow-up showed tags that made the engine raise or compute the wrong method, `src/semantics.py` was changed to refuse any method a code path does not implement and to return a clean error when a tag lacks metadata it needs, and `src/tags.py` gained five consistency rules. The results above were produced before this change (commit `bbc6310`) and were not re-run; re-executing all 455 recorded setup D tool calls on the hardened engine gave identical outputs for 455 of 455. Details: [followup/engine_fix/REPLAY.md](followup/engine_fix/REPLAY.md).

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
