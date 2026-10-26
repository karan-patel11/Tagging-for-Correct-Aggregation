# Expected values for tests/test_semantics.py

**Karan Patel**  
**Date:** 2026-10-25  
**Provenance:** Compiled from primary sources with AI browser assistance. A second pass re-read each of the 33 source values and 14 calculations against the linked pages, and all 47 matched. Karan Patel personally spot-checked these on 2026-10-25: every one of the 33 source values.  

This document records source observations, unit conversions, calculation formulas, and candidate expected results. It is intended for tests/test_semantics.py and eval/verification_log.csv (SPEC §11.3).

Conventions: “as printed” preserves the source number, sign, and scale. “Full value” expresses the amount in USD, USD/share, views, or index points. Formulas distinguish printed observations from derived results. Retrieval date: 2026-10-25.

Before sign-off, personally open each cited source, confirm the value, period, scale, and accession, and independently check the arithmetic. Source collection alone does not satisfy the personal-verification requirement.

## Readiness and unresolved checks

Repo cross-check on 2026-10-25 (Task 2, read-only): the database, raw files and definitions were inspected. Results are recorded in the readiness table. Sections below are updated to match.

| Item | Status | Result / remaining requirement |
|---|---|---|
| Personal verification and sign-off | RESOLVED | Compiled from primary sources with AI browser assistance. A second pass re-read each of the 33 source values and 14 calculations against the linked pages, and all 47 matched. Karan Patel personally spot-checked these on 2026-10-25: every one of the 33 source values. |
| Test 3 database OCF scope | RESOLVED | Scope is continuing operations only, per tag description and SPEC §15. Repo values confirmed in Task 2: YTD9 1250000000, YTD6 661800000 (continuing operations). |
| Test 4 capex concept | RESOLVED | Concept PaymentsToAcquirePropertyPlantAndEquipment; repo FY and YTD9 values match. |
| Test 7 pipeline title | RESOLVED | Two Habit titles summed (Habit_Burger_&_Grill and The_Habit_Burger_Grill). |
| Test 8 definition IDs | RESOLVED | IDs CMG_10K and WING_10K; repo comps match. |
| Test 9 raw CPI comparison | RESOLVED | Raw file data/raw/macro/bls_CUSR0000SEFV.xlsx matches both values. |
| Test 5 eval eligibility | RESOLVED — EXCLUDE FROM EVAL | Recorded quarter-sum and annual EPS both equal 1.14, with a difference of 0.00. Retain the semantic assertion; this question cannot distinguish the aggregation error. |
| Test 10 coverage window | RESOLVED | CMG revenue window starts FY2024. |
| Test 11 and test execution | PENDING | Runs in Phase 7. |

DRI cash-flow scope: operating cash flow from continuing operations only (SPEC §15).

---

## Test 1 and 2: YUM total assets (stock; yearly value = last quarter-end)

| piece | period end | as printed | full value (USD) | form | accession | statement / column |
|---|---|---|---|---|---|---|
| FY2025 year-end | 2025-12-31 | $ 8,197 (in millions) | 8,197,000,000 | 10-K | 0001041061-26-000084 | Consolidated Balance Sheets, p. 61, Total Assets, 2025 column |
| Q1 2025 end | 2025-03-31 | $ 6,659 (in millions) | 6,659,000,000 | 10-Q | 0001041061-25-000025 | Condensed Consolidated Balance Sheets, p. 7, Total Assets, 3/31/2025 column |
| Q2 2025 end | 2025-06-30 | $ 6,917 (in millions) | 6,917,000,000 | 10-Q | 0001041061-25-000057 | Condensed Consolidated Balance Sheets, p. 7, Total Assets, 6/30/2025 column |
| Q3 2025 end | 2025-09-30 | $ 7,193 (in millions) | 7,193,000,000 | 10-Q | 0001041061-25-000109 | Condensed Consolidated Balance Sheets, p. 7, Total Assets, 9/30/2025 column |

- Unit conversions: 8,197 × 1,000,000 = 8,197,000,000; 6,659 × 1,000,000 = 6,659,000,000; 6,917 × 1,000,000 = 6,917,000,000; 7,193 × 1,000,000 = 7,193,000,000 USD.
- Expected FY2025 total assets = FY2025 year-end value = **8,197,000,000 USD**.
- Trap (sum of four quarter-ends) = Q1 + Q2 + Q3 + FY = 6,659,000,000 + 6,917,000,000 + 7,193,000,000 + 8,197,000,000 = **28,966,000,000 USD**.
- Trap (mean of four) = 28,966,000,000 / 4 = **7,241,500,000 USD**.
- These are four point-in-time balances, not four cash flows. The prior-year comparison columns were not used.

Sources: [YUM FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1041061/000104106126000084/yum-20251231.htm), [Q1 10-Q](https://www.sec.gov/Archives/edgar/data/1041061/000104106125000025/yum-20250331.htm), [Q2 10-Q](https://www.sec.gov/Archives/edgar/data/1041061/000104106125000057/yum-20250630.htm), [Q3 10-Q](https://www.sec.gov/Archives/edgar/data/1041061/000104106125000109/yum-20250930.htm).

## Test 3 and 12: DRI operating cash flow, fiscal Q3 2025 (YTD9 − YTD6)

Scope resolved: continuing operations only, per the `fundamentals.op_cash_flow` tag description and the SPEC §15 decisions log.

Scope: operating cash flow from continuing operations only. The discontinued-operations rows are kept for reference and are not used by the test.

| piece | period start | period end | as printed | full value (USD) | form | accession | statement / column |
|---|---|---|---|---|---|---|---|
| YTD9 continuing operations (USED BY TEST) | 2024-05-27 | 2025-02-23 | $ 1,250.0 (in millions) | 1,250,000,000 | 10-Q | 0000940944-25-000018 | Cash flows, pp. 8–9, nine-months current-year column; Net cash provided by operating activities of continuing operations |
| YTD9 discontinued operations (reference only) | 2024-05-27 | 2025-02-23 | (7.9) (in millions) | -7,900,000 | 10-Q | 0000940944-25-000018 | Same statement and column; Net cash used in operating activities of discontinued operations |
| YTD6 continuing operations (USED BY TEST) | 2024-05-27 | 2024-11-24 | $ 661.8 (in millions) | 661,800,000 | 10-Q | 0000940944-25-000003 | Cash flows, pp. 8–9, six-months current-year column; Net cash provided by operating activities of continuing operations |
| YTD6 discontinued operations (reference only) | 2024-05-27 | 2024-11-24 | — (in millions) | 0 | 10-Q | 0000940944-25-000003 | Same statement and column; Net cash (used in) provided by operating activities of discontinued operations |

- Scale conversions: 1,250.0 × 1,000,000 = 1,250,000,000; -7.9 × 1,000,000 = -7,900,000; 661.8 × 1,000,000 = 661,800,000 USD. The source dash represents zero.
- Derived YTD9 total OCF = 1,250,000,000 + (-7,900,000) = **1,242,100,000 USD**.
- Derived YTD6 total OCF = 661,800,000 + 0 = **661,800,000 USD**.
- Expected fiscal Q3 2025 operating cash flow = YTD9 continuing − YTD6 continuing = 1,250,000,000 − 661,800,000 = **588,200,000 USD**.
- Total including discontinued operations: 580,300,000 USD. Recorded as an alternative, not the oracle.
- Expected Q3 period: start = YTD6 end + one day = 2024-11-24 + one day = **2024-11-25**; end = YTD9 end = **2025-02-23**.
- Date check: YTD6 start == YTD9 start? **Yes, both 2024-05-27.** The cash-flow headers print the duration and ending date. Their common start is the day after the prior fiscal year-end, 2024-05-26, shown in the filings; the start is a derived boundary rather than a printed start-date column.
- Trap (un-differenced YTD9) = 1,250,000,000 USD.
- Test 12 check: Q3 start and end both between **2024-11-15 and 2025-03-15**, inclusive? **Yes.** This is a cross-calendar-year fiscal quarter, not CY2025Q1.

Sources: [DRI FY2025 Q3 10-Q](https://www.sec.gov/Archives/edgar/data/940944/000094094425000018/dri-20250223.htm), [DRI FY2025 Q2 10-Q](https://www.sec.gov/Archives/edgar/data/940944/000094094425000003/dri-20241124.htm). The Q2 filing date is 2025-01-02; select by fiscal period rather than assuming a December filing date.

The repo cites the latest-filed accessions, 0000940944-25-000071 (YTD6, FY2026 Q2 10-Q) and 0000940944-26-000009 (YTD9, FY2026 Q3 10-Q), which print the same continuing-operations values as prior-year comparatives (661.8 and 1,250.0, checked by hand on 2026-10-25). The original FY2025 10-Qs (0000940944-25-000003, 0000940944-25-000018) are where the values were first reported. Test 3 asserts that its two sources are the repo-cited accessions.

## Test 4: CMG capex, FY2025 Q4 (FY − YTD9)

**Source values recorded; concept confirmed as PaymentsToAcquirePropertyPlantAndEquipment (see below).**

| piece | period start | period end | as printed | full signed cash flow (USD) | form | accession | statement / line label |
|---|---|---|---|---|---|---|---|
| FY2025 | 2025-01-01 | 2025-12-31 | (666,336) (in thousands) | -666,336,000 | 10-K | 0001058090-26-000009 | Cash flows, p. 39, investing; Purchases of leasehold improvements, property and equipment |
| YTD9 2025 | 2025-01-01 | 2025-09-30 | (468,881) (in thousands) | -468,881,000 | 10-Q | 0001058090-25-000088 | Cash flows, p. 4, nine-months current-year column; same line |

- Scale conversions: -666,336 × 1,000 = -666,336,000; -468,881 × 1,000 = -468,881,000 USD.
- Candidate expected Q4 2025 capex, expressed positively = magnitude(FY) − magnitude(YTD9) = 666,336,000 − 468,881,000 = **197,455,000 USD**.
- Equivalent signed-flow calculation: -[(-666,336,000) − (-468,881,000)] = **197,455,000 USD**.
- Q4 period = **2025-10-01 through 2025-12-31**.
- Exact line label: **Purchases of leasehold improvements, property and equipment**.
- Confirmed Phase 1 concept name: PaymentsToAcquirePropertyPlantAndEquipment (repo FY 666336000 and YTD9 468881000 match).
- Do not select the separately disclosed noncash purchases accrued in accounts payable and accrued liabilities, and do not use net investing cash flow.
- Trap (FY positive capex) = **666,336,000 USD**; trap (YTD9 positive capex) = **468,881,000 USD**.

Sources: [CMG FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1058090/000105809026000009/cmg-20251231.htm), [CMG FY2025 Q3 10-Q](https://www.sec.gov/Archives/edgar/data/1058090/000105809025000088/cmg-20250930.htm).

## Test 5: CMG FY2025 diluted EPS (reported annual, not sum of quarters)

| piece | period end | as printed (USD/share) | full value (USD/share) | form | accession | statement / source |
|---|---|---|---|---|---|---|
| FY2025 annual | 2025-12-31 | $ 1.14 | 1.14 | 10-K | 0001058090-26-000009 | Income and comprehensive income statement, p. 37, Diluted EPS, 2025 column |
| Q1 2025 | 2025-03-31 | $ 0.28 | 0.28 | 10-Q | 0001058090-25-000031 | Income and comprehensive income statement, p. 2, three-months 2025 column |
| Q2 2025 | 2025-06-30 | $ 0.32 | 0.32 | 10-Q | 0001058090-25-000056 | Same statement, p. 2, three-months 2025 column; not six-months 0.61 |
| Q3 2025 | 2025-09-30 | $ 0.29 | 0.29 | 10-Q | 0001058090-25-000088 | Same statement, p. 2, three-months 2025 column; not nine-months 0.89 |
| Q4 2025 | 2025-12-31 | $ 0.25 | 0.25 | 8-K | 0001058090-26-000007 | Exhibit 99.1, Consolidated Statements of Income, three months ended December 31, 2025 |

- EPS has no thousands multiplier. The source statements explicitly exclude per-share data from that scale.
- Expected FY2025 diluted EPS = **1.14 USD/share**.
- Trap (sum of four quarters) = 0.28 + 0.32 + 0.29 + 0.25 = **1.14 USD/share**.
- Absolute difference = |1.14 − 1.14| = **0.00 USD/share**.
- **EXCLUDE THIS QUESTION FROM THE EVAL SET:** 0.00 ≤ 0.02. Retain the semantic test, but its numeric outcome cannot detect summing quarterly EPS for this company-year. Reported annual EPS remains the correct source.

Sources: [annual 10-K](https://www.sec.gov/Archives/edgar/data/1058090/000105809026000009/cmg-20251231.htm), [Q1 10-Q](https://www.sec.gov/Archives/edgar/data/1058090/000105809025000031/cmg-20250331.htm), [Q2 10-Q](https://www.sec.gov/Archives/edgar/data/1058090/000105809025000056/cmg-20250630.htm), [Q3 10-Q](https://www.sec.gov/Archives/edgar/data/1058090/000105809025000088/cmg-20250930.htm), [Q4 earnings exhibit](https://www.sec.gov/Archives/edgar/data/1058090/000105809026000007/cmg-20260203xex991.htm).

## Test 6: combined FY2025 operating margin, CMG + WING (ratio of sums, in percent)

| ticker | fiscal period | revenue as printed | revenue full (USD) | operating income as printed | operating income full (USD) | form | accession | line labels |
|---|---|---|---|---|---|---|---|---|
| CMG | 2025-01-01 through 2025-12-31 | 11,925,601 (in thousands) | 11,925,601,000 | 1,935,798 (in thousands) | 1,935,798,000 | 10-K | 0001058090-26-000009 | Total revenue / Income from operations; income statement, p. 37 |
| WING | FY ended 2025-12-27 | 696,853 (in thousands) | 696,853,000 | 179,291 (in thousands) | 179,291,000 | 10-K | 0001636222-26-000008 | Total revenue / Operating income; comprehensive income statement, p. F-5 |

- Scale conversions: 11,925,601 × 1,000 = 11,925,601,000; 1,935,798 × 1,000 = 1,935,798,000; 696,853 × 1,000 = 696,853,000; 179,291 × 1,000 = 179,291,000 USD.
- Expected combined margin = (OI_CMG + OI_WING) / (Rev_CMG + Rev_WING) × 100 = (1,935,798,000 + 179,291,000) / (11,925,601,000 + 696,853,000) × 100 = 2,115,089,000 / 12,622,454,000 × 100 = **16.7565593822%**.
- CMG margin = 1,935,798,000 / 11,925,601,000 × 100 = **16.2322888381%**.
- WING margin = 179,291,000 / 696,853,000 × 100 = **25.7286687436%**.
- Trap (mean of margins) = [(1,935,798,000 / 11,925,601,000 × 100) + (179,291,000 / 696,853,000 × 100)] / 2 = **20.9804787909%**.
- Absolute separation, using unrounded ratios = **4.22391940867 percentage points**, exceeding the required 0.2 pp.
- Preserve sufficient precision when implementing the oracle. The two companies have different FY2025 ending dates; do not relabel them as identical calendar periods.

Sources: [CMG FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1058090/000105809026000009/cmg-20251231.htm), [WING FY2025 10-K](https://www.sec.gov/Archives/edgar/data/1636222/000163622226000008/wing-20251227.htm).

## Test 7: YUM brand rollup, CY2025Q1 (brand rows only, parent excluded)

Source: [Pageviews Analysis, exact selected filters and titles](https://pageviews.wmcloud.org/?project=en.wikipedia.org&platform=all-access&agent=user&redirects=0&start=2025-01-01&end=2025-03-31&pages=KFC%7CTaco_Bell%7CPizza_Hut%7CHabit_Burger_%26_Grill%7CYum%21_Brands).

Source settings: project en.wikipedia.org; platform All (all-access); agent User; daily date type; dates **2025-01-01 through 2025-03-31**; Include redirects unchecked. The values correspond to the summary table's Views column, not Daily average.

| article (exact title) | grain | total views, as printed | full value (views) | retrieved on |
|---|---|---|---|---|
| KFC | brand | 266,093 | 266093 | 2026-10-25 |
| Taco Bell | brand | 226,860 | 226860 | 2026-10-25 |
| Pizza Hut | brand | 107,956 | 107956 | 2026-10-25 |
| Habit Burger & Grill | brand | 19,169 | 19169 | 2026-10-25 |
| The_Habit_Burger_Grill | brand | 1,302 | 1302 | 2026-10-25 |
| Yum! Brands | parent | 138,002 | 138002 | 2026-10-25 |

- Expected YUM rollup = KFC + Taco Bell + Pizza Hut + Habit_Burger_&_Grill + The_Habit_Burger_Grill = 266093 + 226860 + 107956 + 19169 + 1302 = 620078 + 1302 = 621380 views.
- Trap (including parent) = 621380 + 138002 = 759382 views.
- The dashboard independently prints **758,080** as the five-page total excluding The_Habit_Burger_Grill.
- Habit has two brand articles, summed by date per SPEC §15: Habit_Burger_&_Grill (current title, data from 2024-08-29) and The_Habit_Burger_Grill (former title, still receiving redirect traffic). The spec's old label 'Habit Burger Grill' has no data.
- Pipeline titles confirmed: data/raw/wiki/titles.csv holds Habit_Burger_&_Grill and The_Habit_Burger_Grill; the repo sums them by date (SPEC §15).
- SPEC §15 records Habit as two brand articles summed by date: Habit_Burger_&_Grill and The_Habit_Burger_Grill.
- Canonical title source: [Wikipedia article](https://en.wikipedia.org/wiki/Habit_Burger_%26_Grill).

## Test 8: multi-company comps, FY2025 Q1 (warning, no combined value)

| ticker | fiscal period | actual quarter end | comp as printed | numeric percent | definition_id | release URL (8-K exhibit 99.1) |
|---|---|---|---|---|---|---|
| CMG | FY2025Q1 | 2025-03-31 | Comparable restaurant sales decreased 0.4% | -0.4 | CMG_10K | https://www.sec.gov/Archives/edgar/data/1058090/000105809025000028/cmg-20250423xex991.htm |
| WING | FY2025Q1 | 2025-03-29 | Domestic same store sales growth: 0.5% | 0.5 | WING_10K | https://www.sec.gov/Archives/edgar/data/1636222/000163622225000056/a991wingq12025earningsrele.htm |

- Expected: **status = warning; values = {CMG: -0.4, WING: 0.5}; both company-specific definitions returned; combined value = null**.
- Definition IDs: CMG_10K, WING_10K (confirmed in comps_definitions and comps_quarterly).
- CMG earnings 8-K accession: **0001058090-25-000028**. WING earnings 8-K accession: **0001636222-25-000056**.
- Use the release's headline comp metric. WING's separate company-owned-only figure, 1.4%, is a different metric and is excluded.
- Definition distinction: CMG's FY2025 10-K specifies company-owned restaurants operating at least 13 full calendar months. WING's domestic same-store base requires at least 52 full weeks and includes domestic franchised and company-owned restaurants. The Q1 fiscal ending dates also differ.
- Definition sources: [CMG 10-K, accession 0001058090-26-000009](https://www.sec.gov/Archives/edgar/data/1058090/000105809026000009/cmg-20251231.htm), [WING 10-K, accession 0001636222-26-000008](https://www.sec.gov/Archives/edgar/data/1636222/000163622226000008/wing-20251227.htm).

## Test 9: CPI food away from home (CUSR0000SEFV), Dec 2024 → Dec 2025

Source: [BLS series CUSR0000SEFV](https://data.bls.gov/timeseries/CUSR0000SEFV). Retrieved on **2026-10-25**. The BLS page displayed extraction time **October 25, 2026, 2:06:20 PM**.

Verified metadata on that page: Consumer Price Index for All Urban Consumers; Food away from home in U.S. city average; **Seasonally Adjusted**; base period **1982-84=100**. Source table columns run Jan through Dec. Use the December cells, not an annual average, a published 12-month percent change, or the unadjusted series CUUR0000SEFV.

| month | index level (as printed) | full value (index points) |
|---|---|---|
| 2024-12 | 374.644 | 374.644 |
| 2025-12 | 389.889 | 389.889 |

- Expected pct_change = (Dec 2025 − Dec 2024) / Dec 2024 × 100 = (389.889 − 374.644) / 374.644 × 100 = 15.245 / 374.644 × 100 = **4.06919635707%**.
- Trap (index-point difference) = 389.889 − 374.644 = **15.245 index points**, not a percentage change.
- **Matches raw file: yes.** data/raw/macro/bls_CUSR0000SEFV.xlsx prints 374.644 (Dec 2024) and 389.889 (Dec 2025). The repo's retrieved_on is 2026-10-23.
- Expected: **sum_over_time on CPI is rejected, status = error**. This is an expected assertion, not an observed result from running the repo.
- Additional source finding: the BLS table marks **October 2025 unavailable due to the 2025 lapse in appropriations**. This does not remove the two December observations used here. It does mean a broader pipeline must not invent an October observation.

## Test 10: missing period (insufficient data)

- Request: **CMG revenue for FY2023Q1**.
- Expected under the specified project window: **status = error; explanation contains “insufficient data”; value = null**.
- This expectation is taken from the supplied test contract. Repo coverage window checked in Task 2: CMG revenue starts at FY2024 and has no FY2023 rows. No runtime result is claimed until the tests run.

## Test 11: every ok result has at least one source

- No numeric source observations are needed.
- Expected assertion: every ok result from tests **1, 3, 4, 5, 6, 7 and 9** has at least one source reference supporting the value and its period. Test 8 has the separate warning-and-definitions contract above.
- This assertion has not been run. Tests 4, 7, 8 and 9 depend on resolved mappings and raw-file checks (see readiness table); results must not be reported as passed until the tests run.

---

## SEC filing index audit trail

Official filing indexes and the parent earnings 8-K identify the accessions below. Main-document links appear in the test sections above.

| Used for | accession | form | filing index |
|---|---|---|---|
| YUM FY2025 assets | 0001041061-26-000084 | 10-K | https://www.sec.gov/Archives/edgar/data/1041061/000104106126000084/0001041061-26-000084-index.htm |
| YUM Q1 2025 assets | 0001041061-25-000025 | 10-Q | https://www.sec.gov/Archives/edgar/data/1041061/000104106125000025/0001041061-25-000025-index.htm |
| YUM Q2 2025 assets | 0001041061-25-000057 | 10-Q | https://www.sec.gov/Archives/edgar/data/1041061/000104106125000057/0001041061-25-000057-index.htm |
| YUM Q3 2025 assets | 0001041061-25-000109 | 10-Q | https://www.sec.gov/Archives/edgar/data/1041061/000104106125000109/0001041061-25-000109-index.htm |
| DRI FY2025 Q3 cash flow | 0000940944-25-000018 | 10-Q | https://www.sec.gov/Archives/edgar/data/940944/000094094425000018/0000940944-25-000018-index.htm |
| DRI FY2025 Q2 cash flow | 0000940944-25-000003 | 10-Q | https://www.sec.gov/Archives/edgar/data/940944/000094094425000003/0000940944-25-000003-index.htm |
| CMG FY2025 capex, EPS, margin inputs, definition | 0001058090-26-000009 | 10-K | https://www.sec.gov/Archives/edgar/data/1058090/000105809026000009/0001058090-26-000009-index.htm |
| CMG Q1 EPS | 0001058090-25-000031 | 10-Q | https://www.sec.gov/Archives/edgar/data/1058090/000105809025000031/0001058090-25-000031-index.htm |
| CMG Q2 EPS | 0001058090-25-000056 | 10-Q | https://www.sec.gov/Archives/edgar/data/1058090/000105809025000056/0001058090-25-000056-index.htm |
| CMG Q3 capex and EPS | 0001058090-25-000088 | 10-Q | https://www.sec.gov/Archives/edgar/data/1058090/000105809025000088/0001058090-25-000088-index.htm |
| CMG Q4 EPS | 0001058090-26-000007 | 8-K | https://www.sec.gov/Archives/edgar/data/1058090/000105809026000007/0001058090-26-000007-index.html |
| WING FY2025 margin inputs and definition | 0001636222-26-000008 | 10-K | https://www.sec.gov/Archives/edgar/data/1636222/000163622226000008/0001636222-26-000008-index.htm |
| CMG Q1 comp | 0001058090-25-000028 | 8-K | https://www.sec.gov/Archives/edgar/data/1058090/000105809025000028/0001058090-25-000028-index.html |
| WING Q1 comp | 0001636222-25-000056 | 8-K | https://www.sec.gov/Archives/edgar/data/1636222/000163622225000056/0001636222-25-000056-index.html |

WING Q1 parent 8-K: https://www.sec.gov/Archives/edgar/data/1636222/000163622225000056/wing-20250429.htm . It identifies the April 30, 2025 release as Exhibit 99.1 under Item 2.02. The report-date filename is not the earnings date.

Personal verification and sign-off: Compiled from primary sources with AI browser assistance. A second pass re-read each of the 33 source values and 14 calculations against the linked pages, and all 47 matched. Karan Patel personally spot-checked these on 2026-10-25: every one of the 33 source values. Repository test execution: **pending**.
