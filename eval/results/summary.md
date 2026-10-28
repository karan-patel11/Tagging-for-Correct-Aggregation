# Results summary

Model: claude-haiku-5-5. Run date(s): 2026-10-28. Runs scored: 504. Total cost: $0.4274.

## Accuracy by setup (mean across runs, lowest and highest run)

| Setup | Mean | Min | Max | Behavior accuracy | Over-warning rate | Scaled runs | Unparsed |
|---|---|---|---|---|---|---|---|
| A | 97% | 93% | 100% | 98% | 33% (34) | 8 | 0 |
| B | 94% | 93% | 95% | 100% | 9% (9) | 10 | 0 |
| C | 95% | 93% | 98% | 98% | 19% (19) | 6 | 0 |
| D | 98% | 95% | 100% | 98% | 7% (7) | 1 | 1 |

## Accuracy by setup and category (mean [min, max])

| Category | A | B | C | D |
|---|---|---|---|---|
| comparability_unanswerable | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 95% [86%, 100%] |
| hierarchy | 95% [86%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 95% [86%, 100%] |
| indices | 100% [100%, 100%] | 62% [57%, 71%] | 81% [71%, 86%] | 100% [100%, 100%] |
| ratios | 90% [86%, 100%] | 100% [100%, 100%] | 90% [86%, 100%] | 100% [100%, 100%] |
| time_additivity | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |
| ytd_calendar | 95% [86%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] | 100% [100%, 100%] |

## Trap-hit rate by setup and trap

| Setup | Trap | Hits / runs | Rate |
|---|---|---|---|
| A | average_instead_of_sum | 0 / 9 | 0% |
| A | included_parent_rows | 0 / 21 | 0% |
| A | index_point_difference | 0 / 9 | 0% |
| A | mean_of_4_quarter_ends | 0 / 21 | 0% |
| A | mean_of_margins | 0 / 21 | 0% |
| A | sum_of_4_quarter_ends | 0 / 21 | 0% |
| A | sum_of_index_levels | 0 / 3 | 0% |
| A | used_fiscal_2025 | 0 / 3 | 0% |
| A | used_fiscal_2026 | 0 / 3 | 0% |
| A | used_fy_value | 1 / 21 | 5% |
| A | used_ytd6_value | 0 / 3 | 0% |
| A | used_ytd9_value | 0 / 18 | 0% |
| B | average_instead_of_sum | 0 / 9 | 0% |
| B | included_parent_rows | 0 / 21 | 0% |
| B | index_point_difference | 0 / 9 | 0% |
| B | mean_of_4_quarter_ends | 0 / 21 | 0% |
| B | mean_of_margins | 0 / 21 | 0% |
| B | sum_of_4_quarter_ends | 0 / 21 | 0% |
| B | sum_of_index_levels | 0 / 3 | 0% |
| B | used_fiscal_2025 | 0 / 3 | 0% |
| B | used_fiscal_2026 | 0 / 3 | 0% |
| B | used_fy_value | 0 / 21 | 0% |
| B | used_ytd6_value | 0 / 3 | 0% |
| B | used_ytd9_value | 0 / 18 | 0% |
| C | average_instead_of_sum | 0 / 9 | 0% |
| C | included_parent_rows | 0 / 21 | 0% |
| C | index_point_difference | 0 / 9 | 0% |
| C | mean_of_4_quarter_ends | 0 / 21 | 0% |
| C | mean_of_margins | 0 / 21 | 0% |
| C | sum_of_4_quarter_ends | 0 / 21 | 0% |
| C | sum_of_index_levels | 0 / 3 | 0% |
| C | used_fiscal_2025 | 0 / 3 | 0% |
| C | used_fiscal_2026 | 0 / 3 | 0% |
| C | used_fy_value | 0 / 21 | 0% |
| C | used_ytd6_value | 0 / 3 | 0% |
| C | used_ytd9_value | 0 / 18 | 0% |
| D | average_instead_of_sum | 0 / 9 | 0% |
| D | included_parent_rows | 0 / 21 | 0% |
| D | index_point_difference | 0 / 9 | 0% |
| D | mean_of_4_quarter_ends | 0 / 21 | 0% |
| D | mean_of_margins | 0 / 21 | 0% |
| D | sum_of_4_quarter_ends | 0 / 21 | 0% |
| D | sum_of_index_levels | 0 / 3 | 0% |
| D | used_fiscal_2025 | 0 / 3 | 0% |
| D | used_fiscal_2026 | 0 / 3 | 0% |
| D | used_fy_value | 0 / 21 | 0% |
| D | used_ytd6_value | 0 / 3 | 0% |
| D | used_ytd9_value | 0 / 18 | 0% |

## B vs. C, paired by question

Questions: 42. B right, C wrong: 1 ['q010']. C right, B wrong: 2 ['q022', 'q023']. Both right: 38. Both wrong: 1.

Majority vote across runs (more than half correct). With this sample, a difference of a few questions is within noise.

## Cost of each setup (averages per run)

| Setup | Tool calls | Input | Cache write | Cache read | Output | Cost |
|---|---|---|---|---|---|---|
| A | 2.2 | 3140 | 14 | 2438 | 906 | $0.0999 |
| B | 1.4 | 1369 | 72 | 20342 | 804 | $0.0947 |
| C | 1.3 | 1449 | 68 | 19005 | 819 | $0.0949 |
| D | 3.6 | 6511 | 9 | 3764 | 810 | $0.1380 |

## Unparseable FINAL lines (scored incorrect)

- D: q030 run 1
