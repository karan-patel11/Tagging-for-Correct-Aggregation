# Pre-registration: auto-drafted tags, scored per field and end to end

Written and committed on 2026-10-29, on its own commit, before any model call in this follow-up.
This file is not edited after that commit. Changes of plan go in a dated "Deviations" section of
RESULTS.md.

This follow-up is outside the V2.2 scope in CLAUDE.md; it does not change V2.2 results.

## Hypothesis

A model given only what a vendor would ship (schema, sample rows, vendor documentation) can draft
tags close enough to the hand tags in tags/tags.yaml that setup D's accuracy is unchanged.

## Fixed choices

- Tagging model: claude-sonnet-5-5. Tagging runs once per dataset, offline, and is reviewed by a
  person; answering runs once per analyst question. The answering model stays claude-haiku-5-5.
  This choice is fixed before any run. Any other tagging model would be a separate, separately
  pre-registered run reported alongside this one, not a replacement.
- 3 independent drafts (draft_1, draft_2, draft_3), each one call per tag id (43 ids), same prompt,
  same inputs, default sampling settings.
- Draft 1 is the draft used end to end. This is fixed now, before any draft or score exists.
- Answering model and harness unchanged: claude-haiku-5-5, setup D, the frozen questions
  (questions-frozen tag), eval/run_eval.py's run_one, and the frozen eval/score.py score_run.
- Cost stop: if the estimated total API cost of this follow-up (3 drafts x 43 ids plus 126 setup D
  runs) is over $3, stop before drafting and report.

## Metrics

The hand tags in tags/tags.yaml are the reference.

- **M1** per-field exact match against tags/tags.yaml for the 12 measures (semantic_type in flow,
  stock, ratio, per_share, index, count): semantic_type, unit, additive_over_entities,
  additive_over_time, time_rollup, period_basis, calendar; valid_methods as set equality, with the
  extra and missing methods listed; presence of comparability / hierarchy / seasonal_adjustment /
  annualized where the hand tag has them.
- **M1b** semantic_type exact match for the 31 dimension/identifier entries.
- **M2** dangerous errors: any measure where a draft allows a method the hand tag forbids (a method
  in the draft's valid_methods that is not in the hand tag's), differs on additive_over_time,
  additive_over_entities or time_rollup, or misses a comparability/hierarchy flag.
- **M3** validation: does each draft pass load_tags and check_tags_against_db; every failure is
  listed.
- **M4** end to end: setup D, 42 questions x 3 runs with draft 1, scored by eval/score.py, compared
  with D on hand tags (124/126). Each changed outcome is classified as: wrong answer with no warning
  (silent), tool error/refusal, warning raised, or other, and linked to the tag field that differs.

### Decision rule per field

"Safe to auto-draft" only if all 3 drafts match the hand tag on every measure; otherwise "needs
human review". This threshold is my own choice, not an industry standard.

If draft 1 fails validation (M3), M4 is not run; the validation failures are the M4 result.

Free-text fields (description, derivation, lineage) are not scored; they are listed for a manual
read.

## Design decisions made before any run

1. **Forbidden strings vs the schema.** The strings "ratio_of_sums", "reported_fy_value",
   "Q4 = FY - YTD9" and "latest-filed", every description sentence from tags.yaml and every
   derivation string are banned from every input packet and from the instruction text. The schema
   block may contain "ratio_of_sums" and "reported_fy_value" only as allowed enum values; the schema
   block is generated from the Tag model in src/tags.py plus VALID_METHOD_NAMES, and the leak test
   asserts that it is.
2. **Interface format rules.** The tagger prompt carries three format rules that semantics.py relies
   on but load_tags does not enforce. They are written generically, as interface rules, never tied
   to a table, tag id or column: if an entry has a hierarchy, it is written as
   "<child_grain> -> <parent_col>"; lineage.url is the source's URL; lineage.url_template is the
   source's URL pattern, with placeholders in {braces}. The prompt does not say which entries need
   a hierarchy or which need url_template. The leak test asserts that the format-rules text names no
   table and no tag id.
3. **id, table and filter are copied, not drafted.** They are copied from the input packet into
   every draft and are not scored. For derived.operating_margin the packet states the id and the
   list filter [operating_income, revenue] and nothing else.
4. **Macro vendor metadata.** data/raw/macro/ has no retrieved.json. The raw files themselves carry
   vendor-provided header text, which is used and nothing else (nothing from SPEC.md):
   - bls_CUSR0000SEFV.xlsx header rows: "Consumer Price Index for All Urban Consumers (CPI-U)",
     "Original Data Value", Series Id, "Seasonally Adjusted", Series Title, Area, Item,
     Base Period, Years.
   - census_naics722_sa.xlsx header rows: "U.S. Census Bureau", "Source: Monthly Retail Trade and
     Food Services", "722: Food Services and Drinking Places: U.S. Total", "Seasonally Adjusted
     Sales - Monthly [Millions of Dollars]", "Period: 2024 to 2026", "Data Extracted on: ...".
   The two macro measure packets are linked to their file by series_id as stored in macro_monthly
   (CUSR0000SEFV appears in the BLS header; CENSUS_722_SA is the stored id for the Census file).
   No URL is available from vendor files for either series.
5. **comps_definitions.notes is excluded everywhere.** The notes column is written by the author,
   not the vendor. It is left out of every sample row and every vendor-documentation block. The
   packet for the comps_definitions.notes tag itself gives its name, dtype, null count and distinct
   count only, with no sample values, min/max or distinct values.
6. **Sample rows** are 10 rows of the tag's table (filtered by the tag's filter when it has one),
   drawn with a fixed seed, showing all columns except comps_definitions.notes.
7. **Scoring path check before any paid run.** The per-record scoring (eval/score.py score_run
   applied to each record) is run on the hand-tag eval/results/D.jsonl and must reproduce 124/126
   and the per-question outcomes in eval/results/summary.md. If it does not, the follow-up stops.
8. **"Misses a comparability/hierarchy flag"** (M2) means the hand tag has a value and the draft has
   none or a different one.
9. **M4 changed outcome.** A question's outcome changed if its number of correct runs out of 3
   differs between hand-tag D (eval/results/D.jsonl) and draft-1 D. Each incorrect draft-1 run on a
   changed question is classified, in this order: unparsed or API error -> other; refused = true ->
   tool error/refusal; a run that ended with no numeric answer after a tool error -> tool
   error/refusal; warning = true -> warning raised; otherwise -> silent. The link to a tag field is
   every tag id the run's tool calls named (metric_id or metric) whose draft entry differs from the
   hand entry on any scored field.

## Known limits

- The hand tags are the ground truth, and they were written by me.
- 12 measures; one domain (four restaurant companies, two macro series, Wikipedia pageviews); one
  tagging model.
- For derived.operating_margin the id name itself hints at the answer for that entry.
- 3 runs per question; hand-tag D itself was 124/126, so a changed outcome on one run can be
  answering-model noise and not a tag effect.
