# A_raw: incorrect runs and the most instructive runs

Exploratory, added after seeing the main results (SPEC §15, 2026-11-01). A_raw is setup A on
`data/warehouse_raw.duckdb`: the same tables without the meaning columns (fundamentals:
`period_basis`, `fiscal_year`, `fiscal_quarter`, `concept`; brand_attention_daily: `grain`, `brand`).
Scored with the unchanged `eval/score.py`; the counts below are from `eval/results/summary.json`
(`exploratory.setups.A_raw`) and the transcripts in `eval/results/A_raw.jsonl`.

## Every incorrect run

None. All 126 of 126 A_raw runs scored correct: no wrong number, no trap hit, no missing warning,
no wrong refusal, and no unparseable FINAL line.

| Question | Category | Run | Trap hit | What happened | SQL |
|---|---|---|---|---|---|
| (none) | | | | | |

Because no run failed, §11.7's "two most instructive failures" cannot be filled with failures. The
three runs below scored correct but show what the scorer does not check, and where removing the
meaning columns changed the model's reasoning.

## The three most instructive runs

### 1. q016, runs 1 and 2 (ytd_calendar): correct number, wrong description of it

Question: Darden's net cash from operating activities from continuing operations in fiscal Q3 2025.
All three runs returned 588.2 million (nine-month YTD minus six-month YTD), which is the answer key.
But runs 1 and 2 told the analyst the opposite of the truth: "The data has no continuing-operations
breakdown, so this is total operating cash flow" (run 1) and "this figure is total operating cash
flow. It may differ slightly from the continuing-operations line in the filing" (run 2). Darden's
`op_cash_flow` rows are the continuing-operations concept (SPEC §15 decisions log); the only column
that said so, `concept`, was removed in A_raw. Run 3 stated the limit correctly: "I can't confirm
that the figure excludes discontinued operations." The scorer checks the number and the warning
flag, not the explanation, so all three runs count as correct.

What would fix it: keep the basis of a metric in the data or its tag (here the XBRL concept, or a
tag description that says "from continuing operations"), so the model can confirm the basis instead
of guessing it.

SQL (run 1, last query):

```sql
SELECT metric, period_start, period_end, form, filed, value, accession FROM fundamentals WHERE ticker = 'DRI' AND metric = 'op_cash_flow' ORDER BY period_end, period_start
```

### 2. q017, all three runs (ytd_calendar): the fiscal-Q4 trap did not fire without the fiscal labels

Question: Darden's total revenue in fiscal Q4 2026 (the 14-week quarter ended May 31, 2026). In
setup A, run 2 reported the full-year 10-K row, the only stored-trap hit in the main run; that row
is stored with `fiscal_quarter` 4. In A_raw there is no `fiscal_quarter` column, and all three runs
read the row as what its dates say it is (May 26, 2025 to May 31, 2026, a full year), then derived
Q4 as full year minus the nine-month YTD: 3,718.8 million. Two runs also checked that the three
reported quarters sum to the nine-month figure. This is one question and one trap hit, so it shows
how the label could mislead, not that removing labels helps in general.

What would fix it in the tagged setups: a fiscal-quarter label on a full-year row is ambiguous; the
tag or the column should say that fiscal_quarter 4 on an FY row means "the year ending in Q4", not
"the fourth quarter alone".

SQL (run 3):

```sql
SELECT ticker, cik, metric, value, unit, period_start, period_end, form, accession, filed FROM fundamentals WHERE ticker = 'DRI' AND metric ILIKE '%revenue%' ORDER BY period_end DESC LIMIT 50
```

### 3. q010, runs 1 and 2 (ratios): the warning flag was right, the stated reason was not the expected one

Question: the combined operating margin of Chipotle, Yum! Brands and Darden for fiscal 2025. q010 is
the only question where A and A_raw differ by majority vote: A runs 1 and 2 returned 18.23% without
the expected mixed-fiscal-calendar warning; all three A_raw runs set `warning: true`. But the caveat
A_raw runs 1 and 2 actually wrote was about the word "combined" (pooled ratio vs. simple average of
margins, 19.6%), not about Darden's May year end next to the December year ends; only run 3 named
the period mismatch. The scorer checks that warning is true, not why, so the one discordant question
partly reflects the flag rather than the reasoning.

What would fix it: if the reason for a warning matters, score it (for example, require the
expected caveat in the text); until then, a one-question difference in warning flags should not be
read as better reasoning.

SQL (run 1, first query):

```sql
SELECT ticker, metric, unit, period_start, period_end, form, value, filed FROM fundamentals WHERE ticker IN ('CMG','YUM','DRI') AND metric ILIKE '%operat%' OR (ticker IN ('CMG','YUM','DRI') AND metric ILIKE '%revenue%') ORDER BY ticker, period_end DESC, metric LIMIT 200
```

## What this does and does not show

- A vs. A_raw differ on one question of 42 (q010) by majority vote; the exact two-sided sign test
  gives p = 1.00, so there is no detectable difference.
- Removing the meaning columns did not make setup A worse on these questions; with this sample it
  also cannot show that it made A better.
- The cost of losing the columns showed up in the explanations (q016), which the scorer does not
  grade.
