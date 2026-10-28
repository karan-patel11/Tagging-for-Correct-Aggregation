# Results summary

Model: claude-haiku-5-5. Run date(s): not recorded. Runs scored: 20. Total cost: $0.0161.

## Accuracy by setup (mean across runs, lowest and highest run)

| Setup | Mean | Min | Max | Behavior accuracy | Over-warning rate | Scaled runs | Unparsed |
|---|---|---|---|---|---|---|---|
| A | 100% | 100% | 100% | 100% | 50% (2) | 1 | 0 |
| B | 100% | 100% | 100% | 100% | 50% (2) | 0 | 0 |
| C | 100% | 100% | 100% | 100% | 25% (1) | 0 | 0 |
| D | 100% | 100% | 100% | 100% | 25% (1) | 0 | 0 |

## Accuracy by setup and category (mean [min, max])

| Category | A | B | C | D |
|---|---|---|---|---|
| comparability_unanswerable | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |
| indices | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |
| ratios | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |
| time_additivity | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |
| ytd_calendar | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |

## Trap-hit rate by setup and trap

| Setup | Trap | Hits / runs | Rate |
|---|---|---|---|
| A | index_point_difference | 0 / 1 | 0% |
| A | mean_of_4_quarter_ends | 0 / 1 | 0% |
| A | mean_of_margins | 0 / 1 | 0% |
| A | sum_of_4_quarter_ends | 0 / 1 | 0% |
| A | used_fiscal_2026 | 0 / 1 | 0% |
| A | used_fy_value | 0 / 1 | 0% |
| A | used_ytd9_value | 0 / 1 | 0% |
| B | index_point_difference | 0 / 1 | 0% |
| B | mean_of_4_quarter_ends | 0 / 1 | 0% |
| B | mean_of_margins | 0 / 1 | 0% |
| B | sum_of_4_quarter_ends | 0 / 1 | 0% |
| B | used_fiscal_2026 | 0 / 1 | 0% |
| B | used_fy_value | 0 / 1 | 0% |
| B | used_ytd9_value | 0 / 1 | 0% |
| C | index_point_difference | 0 / 1 | 0% |
| C | mean_of_4_quarter_ends | 0 / 1 | 0% |
| C | mean_of_margins | 0 / 1 | 0% |
| C | sum_of_4_quarter_ends | 0 / 1 | 0% |
| C | used_fiscal_2026 | 0 / 1 | 0% |
| C | used_fy_value | 0 / 1 | 0% |
| C | used_ytd9_value | 0 / 1 | 0% |
| D | index_point_difference | 0 / 1 | 0% |
| D | mean_of_4_quarter_ends | 0 / 1 | 0% |
| D | mean_of_margins | 0 / 1 | 0% |
| D | sum_of_4_quarter_ends | 0 / 1 | 0% |
| D | used_fiscal_2026 | 0 / 1 | 0% |
| D | used_fy_value | 0 / 1 | 0% |
| D | used_ytd9_value | 0 / 1 | 0% |

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

## Unparseable FINAL lines (scored incorrect)

None.
