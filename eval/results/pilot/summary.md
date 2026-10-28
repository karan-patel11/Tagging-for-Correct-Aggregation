# Results summary

Model: claude-haiku-5-5. Run date(s): not recorded. Runs scored: 20. Total cost: $0.0161.

## Accuracy by setup (mean across runs, lowest and highest run)

| Setup | Correct runs | Mean | Min | Max | Behavior accuracy | Unparsed |
|---|---|---|---|---|---|---|
| A | 5 / 5 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| B | 5 / 5 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| C | 5 / 5 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| D | 5 / 5 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |

## Over-warning and scale conversion by setup

Over-warning: warning = true on a question whose expected behavior is answer, as a fraction of all runs on those questions (not scored incorrect). Scale-converted: runs whose FINAL unit named thousands, millions or billions relative to the question's unit and was converted before scoring.

| Setup | Over-warned runs / answer-question runs | Over-warning rate | Scale-converted runs |
|---|---|---|---|
| A | 2 / 4 | 50.0% | 1 |
| B | 2 / 4 | 50.0% | 0 |
| C | 1 / 4 | 25.0% | 0 |
| D | 1 / 4 | 25.0% | 0 |

## Accuracy by setup and category (mean [min, max])

| Category | A | B | C | D |
|---|---|---|---|---|
| comparability_unanswerable | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| indices | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| ratios | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| time_additivity | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| ytd_calendar | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |

## Trap-hit rate by setup and trap

| Setup | Trap | Hits / runs | Rate |
|---|---|---|---|
| A | index_point_difference | 0 / 1 | 0.0% |
| A | mean_of_4_quarter_ends | 0 / 1 | 0.0% |
| A | mean_of_margins | 0 / 1 | 0.0% |
| A | sum_of_4_quarter_ends | 0 / 1 | 0.0% |
| A | used_fiscal_2026 | 0 / 1 | 0.0% |
| A | used_fy_value | 0 / 1 | 0.0% |
| A | used_ytd9_value | 0 / 1 | 0.0% |
| B | index_point_difference | 0 / 1 | 0.0% |
| B | mean_of_4_quarter_ends | 0 / 1 | 0.0% |
| B | mean_of_margins | 0 / 1 | 0.0% |
| B | sum_of_4_quarter_ends | 0 / 1 | 0.0% |
| B | used_fiscal_2026 | 0 / 1 | 0.0% |
| B | used_fy_value | 0 / 1 | 0.0% |
| B | used_ytd9_value | 0 / 1 | 0.0% |
| C | index_point_difference | 0 / 1 | 0.0% |
| C | mean_of_4_quarter_ends | 0 / 1 | 0.0% |
| C | mean_of_margins | 0 / 1 | 0.0% |
| C | sum_of_4_quarter_ends | 0 / 1 | 0.0% |
| C | used_fiscal_2026 | 0 / 1 | 0.0% |
| C | used_fy_value | 0 / 1 | 0.0% |
| C | used_ytd9_value | 0 / 1 | 0.0% |
| D | index_point_difference | 0 / 1 | 0.0% |
| D | mean_of_4_quarter_ends | 0 / 1 | 0.0% |
| D | mean_of_margins | 0 / 1 | 0.0% |
| D | sum_of_4_quarter_ends | 0 / 1 | 0.0% |
| D | used_fiscal_2026 | 0 / 1 | 0.0% |
| D | used_fy_value | 0 / 1 | 0.0% |
| D | used_ytd9_value | 0 / 1 | 0.0% |

## B vs. C, paired by question

Questions: 5. B right, C wrong: 0 []. C right, B wrong: 0 []. Both right: 5. Both wrong: 0.

Majority vote across runs (more than half correct). With this sample, a difference of a few questions is within noise.

## Cost of each setup (averages per run)

| Setup | Tool calls | Input | Cache write | Cache read | Output | Cost |
|---|---|---|---|---|---|---|
| A | 2.6 | 2448 | 355 | 2131 | 964 | $0.0040 |
| B | 1.6 | 1065 | 1811 | 18114 | 786 | $0.0045 |
| C | 1.4 | 1060 | 1723 | 17228 | 720 | $0.0043 |
| D | 2.2 | 3451 | 216 | 2803 | 534 | $0.0033 |

## Mean tool calls and tokens per question (mean across runs; tokens = input + cache write + cache read + output)

| Question | A tools | A tokens | B tools | B tokens | C tools | C tokens | D tools | D tokens |
|---|---|---|---|---|---|---|---|---|
| q003 | 2.0 | 3,787 | 1.0 | 19,342 | 1.0 | 18,298 | 1.0 | 2,904 |
| q007 | 1.0 | 7,071 | 1.0 | 21,601 | 1.0 | 20,506 | 3.0 | 9,031 |
| q016 | 3.0 | 6,868 | 2.0 | 20,004 | 1.0 | 19,118 | 2.0 | 6,578 |
| q018 | 2.0 | 4,407 | 1.0 | 19,006 | 1.0 | 18,154 | 4.0 | 12,298 |
| q038 | 5.0 | 7,357 | 3.0 | 28,928 | 3.0 | 27,581 | 1.0 | 4,204 |

## Unparseable FINAL lines (scored incorrect)

None.
