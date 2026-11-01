# Results summary

Model: claude-haiku-5-5. Run date(s): 2026-10-28. Runs scored: 504. Total cost: $0.4274.

## Scorer bug (fixed before this summary)

The scale-word pattern used \b, which treats "_" as part of a word, so a FINAL unit of "USD_millions" was read as unscaled while the question unit "USD millions" was read as millions, and correct answers were divided by 1,000,000. The scoring rule did not change: a unit that names millions is converted; the code had not applied it to this spelling.

Fixed in commit 4977d48. 12 runs flipped (B 8, C 4), all on q022, q023, q024, incorrect to correct; no other field changed except number_ok on the same runs.

| Setup | Correct before fix | Correct after fix |
|---|---|---|
| A | 122 | 122 |
| B | 118 | 126 |
| C | 120 | 124 |
| D | 124 | 124 |

## Accuracy by setup (mean across runs, lowest and highest run)

| Setup | Correct runs | Mean | Min | Max | Behavior accuracy | Unparsed |
|---|---|---|---|---|---|---|
| A | 122 / 126 | 96.8% | 92.9% | 100.0% | 98.4% | 0 |
| B | 126 / 126 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |
| C | 124 / 126 | 98.4% | 97.6% | 100.0% | 98.4% | 0 |
| D | 124 / 126 | 98.4% | 95.2% | 100.0% | 98.4% | 1 |

## Over-warning and scale conversion by setup

Over-warning: warning = true on a question whose expected behavior is answer, as a fraction of all runs on those questions (not scored incorrect). Scale-converted: runs whose FINAL unit named thousands, millions or billions relative to the question's unit and was converted before scoring.

| Setup | Over-warned runs / answer-question runs | Over-warning rate | Scale-converted runs |
|---|---|---|---|
| A | 34 / 102 | 33.3% | 8 |
| B | 9 / 102 | 8.8% | 2 |
| C | 19 / 102 | 18.6% | 2 |
| D | 7 / 102 | 6.9% | 1 |

## Accuracy by setup and category (mean [min, max])

| Category | A | B | C | D |
|---|---|---|---|---|
| comparability_unanswerable | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 95.2% [85.7%, 100.0%] |
| hierarchy | 95.2% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 95.2% [85.7%, 100.0%] |
| indices | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| ratios | 90.5% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] | 90.5% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] |
| time_additivity | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| ytd_calendar | 95.2% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |

## Trap-hit rate by setup and trap

| Setup | Trap | Hits / runs | Rate |
|---|---|---|---|
| A | average_instead_of_sum | 0 / 9 | 0.0% |
| A | included_parent_rows | 0 / 21 | 0.0% |
| A | index_point_difference | 0 / 9 | 0.0% |
| A | mean_of_4_quarter_ends | 0 / 21 | 0.0% |
| A | mean_of_margins | 0 / 21 | 0.0% |
| A | sum_of_4_quarter_ends | 0 / 21 | 0.0% |
| A | sum_of_index_levels | 0 / 3 | 0.0% |
| A | used_fiscal_2025 | 0 / 3 | 0.0% |
| A | used_fiscal_2026 | 0 / 3 | 0.0% |
| A | used_fy_value | 1 / 21 | 4.8% |
| A | used_ytd6_value | 0 / 3 | 0.0% |
| A | used_ytd9_value | 0 / 18 | 0.0% |
| B | average_instead_of_sum | 0 / 9 | 0.0% |
| B | included_parent_rows | 0 / 21 | 0.0% |
| B | index_point_difference | 0 / 9 | 0.0% |
| B | mean_of_4_quarter_ends | 0 / 21 | 0.0% |
| B | mean_of_margins | 0 / 21 | 0.0% |
| B | sum_of_4_quarter_ends | 0 / 21 | 0.0% |
| B | sum_of_index_levels | 0 / 3 | 0.0% |
| B | used_fiscal_2025 | 0 / 3 | 0.0% |
| B | used_fiscal_2026 | 0 / 3 | 0.0% |
| B | used_fy_value | 0 / 21 | 0.0% |
| B | used_ytd6_value | 0 / 3 | 0.0% |
| B | used_ytd9_value | 0 / 18 | 0.0% |
| C | average_instead_of_sum | 0 / 9 | 0.0% |
| C | included_parent_rows | 0 / 21 | 0.0% |
| C | index_point_difference | 0 / 9 | 0.0% |
| C | mean_of_4_quarter_ends | 0 / 21 | 0.0% |
| C | mean_of_margins | 0 / 21 | 0.0% |
| C | sum_of_4_quarter_ends | 0 / 21 | 0.0% |
| C | sum_of_index_levels | 0 / 3 | 0.0% |
| C | used_fiscal_2025 | 0 / 3 | 0.0% |
| C | used_fiscal_2026 | 0 / 3 | 0.0% |
| C | used_fy_value | 0 / 21 | 0.0% |
| C | used_ytd6_value | 0 / 3 | 0.0% |
| C | used_ytd9_value | 0 / 18 | 0.0% |
| D | average_instead_of_sum | 0 / 9 | 0.0% |
| D | included_parent_rows | 0 / 21 | 0.0% |
| D | index_point_difference | 0 / 9 | 0.0% |
| D | mean_of_4_quarter_ends | 0 / 21 | 0.0% |
| D | mean_of_margins | 0 / 21 | 0.0% |
| D | sum_of_4_quarter_ends | 0 / 21 | 0.0% |
| D | sum_of_index_levels | 0 / 3 | 0.0% |
| D | used_fiscal_2025 | 0 / 3 | 0.0% |
| D | used_fiscal_2026 | 0 / 3 | 0.0% |
| D | used_fy_value | 0 / 21 | 0.0% |
| D | used_ytd6_value | 0 / 3 | 0.0% |
| D | used_ytd9_value | 0 / 18 | 0.0% |

## B vs. C, paired by question

Questions: 42. B right, C wrong: 1 ['q010']. C right, B wrong: 0 []. Both right: 41. Both wrong: 0.

Majority vote across runs (more than half correct). With this sample, a difference of a few questions is within noise.

## Cost of each setup (averages per run)

| Setup | Tool calls | Input | Cache write | Cache read | Output | Cost |
|---|---|---|---|---|---|---|
| A | 2.2 | 3140 | 14 | 2438 | 906 | $0.0999 |
| B | 1.4 | 1369 | 72 | 20342 | 804 | $0.0947 |
| C | 1.3 | 1449 | 68 | 19005 | 819 | $0.0949 |
| D | 3.6 | 6511 | 9 | 3764 | 810 | $0.1380 |

## Mean tool calls and tokens per question (mean across runs; tokens = input + cache write + cache read + output)

| Question | A tools | A tokens | B tools | B tokens | C tools | C tokens | D tools | D tokens |
|---|---|---|---|---|---|---|---|---|
| q001 | 1.0 | 2,954 | 1.0 | 19,159 | 1.0 | 18,350 | 1.0 | 2,898 |
| q002 | 1.3 | 3,105 | 1.3 | 19,347 | 1.0 | 18,276 | 1.0 | 2,918 |
| q003 | 1.0 | 3,112 | 1.0 | 19,214 | 1.0 | 18,470 | 1.0 | 2,905 |
| q004 | 1.7 | 3,133 | 1.0 | 19,084 | 1.3 | 18,442 | 1.3 | 3,288 |
| q005 | 1.0 | 3,036 | 1.0 | 19,211 | 1.0 | 18,321 | 2.3 | 5,566 |
| q006 | 1.3 | 2,904 | 1.0 | 19,129 | 1.0 | 18,271 | 1.7 | 4,083 |
| q007 | 2.7 | 10,105 | 1.0 | 21,591 | 1.0 | 20,438 | 3.7 | 10,606 |
| q008 | 2.0 | 10,244 | 1.0 | 21,632 | 1.0 | 20,305 | 4.0 | 10,658 |
| q009 | 2.7 | 13,736 | 1.0 | 21,802 | 1.0 | 21,032 | 3.0 | 12,401 |
| q010 | 2.3 | 9,651 | 1.7 | 29,981 | 1.0 | 22,397 | 4.7 | 13,242 |
| q011 | 2.3 | 9,819 | 1.0 | 21,177 | 1.0 | 20,472 | 3.0 | 8,931 |
| q012 | 2.7 | 7,542 | 1.3 | 23,886 | 1.3 | 22,681 | 3.0 | 9,371 |
| q013 | 1.7 | 7,304 | 2.0 | 31,539 | 2.0 | 26,910 | 1.7 | 5,505 |
| q014 | 1.7 | 4,497 | 1.3 | 20,244 | 1.0 | 19,385 | 4.0 | 9,074 |
| q015 | 1.0 | 3,682 | 1.3 | 19,802 | 1.3 | 23,059 | 4.3 | 10,925 |
| q016 | 2.7 | 7,137 | 1.3 | 20,146 | 1.0 | 18,967 | 2.0 | 5,247 |
| q017 | 1.0 | 4,257 | 1.0 | 19,990 | 1.0 | 19,239 | 4.7 | 14,141 |
| q018 | 2.0 | 4,752 | 1.0 | 19,127 | 1.0 | 18,152 | 3.7 | 12,011 |
| q019 | 2.0 | 4,489 | 1.3 | 22,169 | 1.0 | 18,186 | 3.3 | 11,859 |
| q020 | 2.3 | 5,352 | 1.3 | 19,299 | 1.3 | 18,421 | 3.3 | 11,963 |
| q021 | 2.0 | 4,433 | 1.0 | 19,004 | 1.0 | 18,167 | 3.0 | 11,699 |
| q022 | 2.3 | 4,652 | 1.0 | 19,047 | 1.0 | 18,232 | 3.3 | 11,854 |
| q023 | 2.7 | 5,120 | 1.0 | 19,017 | 1.0 | 18,280 | 3.0 | 11,586 |
| q024 | 1.3 | 3,911 | 1.0 | 19,085 | 1.3 | 21,389 | 3.3 | 11,768 |
| q025 | 2.7 | 6,783 | 1.0 | 19,754 | 2.0 | 25,741 | 3.7 | 15,850 |
| q026 | 2.3 | 7,156 | 1.3 | 19,963 | 2.0 | 22,666 | 3.3 | 14,418 |
| q027 | 2.7 | 7,848 | 1.7 | 20,029 | 1.7 | 22,274 | 3.7 | 15,890 |
| q028 | 2.3 | 5,302 | 2.3 | 32,833 | 1.7 | 26,318 | 3.3 | 13,681 |
| q029 | 3.0 | 7,867 | 1.0 | 19,415 | 1.3 | 18,679 | 4.0 | 16,484 |
| q030 | 2.3 | 7,008 | 1.0 | 20,019 | 1.7 | 25,768 | 11.7 | 23,603 |
| q031 | 1.7 | 5,037 | 2.7 | 33,875 | 1.7 | 25,681 | 8.7 | 20,241 |
| q032 | 1.3 | 3,659 | 1.0 | 19,738 | 1.0 | 18,818 | 6.3 | 22,918 |
| q033 | 1.3 | 3,809 | 1.3 | 19,911 | 1.0 | 18,948 | 6.3 | 20,754 |
| q034 | 1.3 | 5,689 | 1.0 | 19,632 | 1.3 | 19,140 | 7.3 | 22,534 |
| q035 | 4.3 | 6,837 | 3.0 | 30,188 | 2.3 | 25,318 | 2.0 | 7,248 |
| q036 | 5.0 | 10,049 | 3.0 | 33,055 | 2.0 | 28,435 | 2.0 | 7,216 |
| q037 | 4.0 | 13,149 | 3.7 | 47,955 | 3.0 | 38,997 | 3.3 | 8,745 |
| q038 | 5.3 | 8,455 | 2.3 | 26,979 | 2.3 | 21,653 | 1.0 | 4,226 |
| q039 | 1.3 | 4,009 | 1.0 | 19,135 | 1.0 | 18,334 | 1.3 | 3,535 |
| q040 | 3.0 | 14,766 | 1.0 | 20,941 | 1.0 | 20,127 | 6.3 | 13,171 |
| q041 | 2.3 | 11,466 | 1.0 | 21,125 | 1.0 | 20,080 | 5.0 | 12,845 |
| q042 | 1.7 | 5,098 | 1.0 | 20,420 | 1.3 | 23,520 | 3.0 | 8,099 |

## Unparseable FINAL lines (scored incorrect)

- D: q030 run 1

## Exploratory: setup A_raw (added after seeing the main results)

Added after seeing the main results (SPEC section 15, 2026-11-01). A_raw is setup A on data/warehouse_raw.duckdb: the same tables with the meaning columns removed (fundamentals: period_basis, fiscal_year, fiscal_quarter, concept; brand_attention_daily: grain, brand). Same questions, answer key, model, instructions and scorer. Not one of the planned A-D comparisons and never mixed into their tables.

Model: claude-haiku-5-5. Run date(s): 2026-11-01. Runs scored: 126 (3 per question). Cost: $0.0901.

A is repeated from the tables above for reference only.

| Setup | Correct runs | Mean | Min | Max | Behavior accuracy | Unparsed |
|---|---|---|---|---|---|---|
| A (reference) | 122 / 126 | 96.8% | 92.9% | 100.0% | 98.4% | 0 |
| A_raw | 126 / 126 | 100.0% | 100.0% | 100.0% | 100.0% | 0 |

### A_raw: accuracy by category (mean [min, max])

| Category | A (reference) | A_raw |
|---|---|---|
| comparability_unanswerable | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| hierarchy | 95.2% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] |
| indices | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| ratios | 90.5% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] |
| time_additivity | 100.0% [100.0%, 100.0%] | 100.0% [100.0%, 100.0%] |
| ytd_calendar | 95.2% [85.7%, 100.0%] | 100.0% [100.0%, 100.0%] |

### A_raw: trap hits

| Trap | A (reference) hits / runs | A_raw hits / runs |
|---|---|---|
| average_instead_of_sum | 0 / 9 | 0 / 9 |
| included_parent_rows | 0 / 21 | 0 / 21 |
| index_point_difference | 0 / 9 | 0 / 9 |
| mean_of_4_quarter_ends | 0 / 21 | 0 / 21 |
| mean_of_margins | 0 / 21 | 0 / 21 |
| sum_of_4_quarter_ends | 0 / 21 | 0 / 21 |
| sum_of_index_levels | 0 / 3 | 0 / 3 |
| used_fiscal_2025 | 0 / 3 | 0 / 3 |
| used_fiscal_2026 | 0 / 3 | 0 / 3 |
| used_fy_value | 1 / 21 | 0 / 21 |
| used_ytd6_value | 0 / 3 | 0 / 3 |
| used_ytd9_value | 0 / 18 | 0 / 18 |

### A_raw: cost (averages per run)

| Setup | Tool calls | Input | Cache write | Cache read | Output | Cost |
|---|---|---|---|---|---|---|
| A (reference) | 2.2 | 3140 | 14 | 2438 | 906 | $0.0999 |
| A_raw | 2.2 | 2486 | 0 | 2240 | 888 | $0.0901 |

Over-warned runs / answer-question runs: A_raw 37 / 102 (A 34 / 102). Scale-converted runs: A_raw 13 (A 8). Unparseable FINAL lines in A_raw: none.

### A vs. A_raw, paired by question

Questions: 42. A right, A_raw wrong: 0 []. A_raw right, A wrong: 1 ['q010']. Both right: 41. Both wrong: 0. Exact two-sided sign test (McNemar) on discordant questions: p = 1.00 (a difference is reported only if p < 0.05; otherwise no detectable difference).

Majority vote across runs (more than half correct). With this sample, a difference of a few questions is within noise.
