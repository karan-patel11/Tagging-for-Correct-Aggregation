# Error analysis

Terms and question texts: see [key.md](key.md).

This analysis uses the stored full-run transcripts in `eval/results/{A,B,C,D}.jsonl` and the corrected [summary](../eval/results/summary.md). It was prepared with coding assistance; it does not assert a personal source-verification sign-off. No prompts, tools, frozen questions or recorded runs were changed for this analysis. Suggested remedies below are hypotheses for a future evaluation, not measured improvements.

The recorded run starts fall on October 28, 2026 UTC (October 27 Eastern). Each setup has 126 runs. A has four incorrect runs, B has none, C has two, and D has two. These are run outcomes, not eight distinct failed questions. Unparsed output counts as incorrect.

## A: schema and SQL

- **q017, run 2 — annual revenue substituted for a quarter.** The response actually calculated Darden's fiscal Q4 2026 revenue as $3,718.8 million in its explanation, but put the full-year $13,210.9 million in FINAL, matching `used_fy_value`; its other two runs answered correctly. A possible remedy is to verify the FINAL period against the requested period and the derivation before emitting it.
- **q031, run 2 — arithmetic after a correct retrieval.** The response listed KFC views of 313,786 and a combined total of 601,924, but reported 52.3% instead of approximately 52.1305%, outside the 0.1 percentage-point tolerance. Computing the division directly in SQL would avoid this particular handwritten calculation error.

The other two A failures are q010 runs 1 and 2: both returned the correct combined margin but omitted the required mixed-fiscal-calendar warning. That is a behavior error, not a mean-of-margins trap hit.

## B: prose and SQL

B has no scored failures: 126 of 126 runs are correct under the frozen scoring rules. There are therefore no two incorrect B examples to select. Its nine over-warning cases are a secondary measure and are not scored as incorrect; two examples illustrate that distinction:

- **q012, run 1.** B correctly derived Chipotle's Q2 cash flow as $561,327,000 but flagged later comparative filing dates as a caveat; a possible refinement is to explain the latest-filed comparative lineage without treating a later filing date alone as evidence of defective data.
- **q014, run 1.** B correctly derived Chipotle's Q4 capex as $197,455,000, then warned about unrelated Q1 and YTD6 metadata that did not feed that calculation; a possible refinement is to restrict caveats to evidence relevant to the requested calculation.

These observations do not establish that all extra warnings are substantively wrong. The secondary metric records a warning on a question labelled `answer`, rather than adjudicating every caveat's wording.

## C: tags and SQL

C's only two incorrect runs are on the same question, so they are not two independent failure types:

- **q010, run 1.** C returned 18.23% with `warning: false`, although its table showed Darden's May year end next to the other companies' December year ends; checking the source-period alignment before finalizing the warning flag could address this omission.
- **q010, run 2.** C again returned 18.23% with `warning: false` while listing those different year ends; the same proposed period-alignment check applies. Run 3 supplied the required warning and was correct.

The tags preserved the ratio-of-sums arithmetic here; seeing a fiscal-calendar description did not reliably cause the model to set the required warning flag. This is an observation about these runs, not evidence that tags generally help or harm performance.

## D: semantic tools

- **q030, run 1 — interface mismatch and failed recovery.** D requested full-year pageviews using a month range, received errors explaining that calendar quarters were required, and ended with `max_tokens` and no FINAL line. Its other two runs recovered using quarterly requests, so the data and a compositional route were available; clearer period-format guidance or a future annual wrapper could reduce this friction.
- **q034, run 1 — failed discovery of the comps retrieval route.** D tried unsupported comps lookups through `get_metric` and disallowed single-company aggregation calls, then refused an answerable question. Its other two runs used a multi-company `aggregate` request that returns the individual values and definitions in a warning envelope; making that supported route discoverable could address this failure without treating comps as additive.

Neither example proves that the question is impossible with D's tools. The direct interfaces have coverage limitations, and the successful runs demonstrate the available workarounds. The frozen tools and their descriptions remain unchanged.

## Scoring disclosure and interpretation

The unit parser originally treated `USD_millions` differently from `USD millions`. Commit `4977d48` fixed that spelling bug without changing the rule: units naming millions must be converted. Twelve runs changed from incorrect to correct (eight B and four C), all on q022–q024. The raw model outputs were preserved; the summary and page show corrected scores and before/after counts.

B and C have the same majority-vote outcome on 41 of 42 questions; q010 is the only difference. With this sample and no statistical significance test, the results do not establish that either format is better. D changes interface and enforcement together, so its performance cannot isolate enforcement's causal effect.

The author wrote both the questions and the system. Most questions were drafted before the core logic, while four replacements were added afterwards; all were frozen before evaluation. The financial window is fiscal 2024–2025 for CMG, WING and YUM, and fiscal 2025–2026 for Darden. These design limits, the one-model sample and pageviews as a proxy restrict generalization.
