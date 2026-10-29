# Deviations from PREREG.md

Changes of plan, and decisions PREREG.md does not cover, each dated when it was made. PREREG.md
itself is never edited. build_results.py copies this file into the Deviations section of
RESULTS.md.

## 2026-10-28 (before any drafting)
- Cost cap raised from $3.00 to $3.75 after the cost check (estimate $2.5720, upper bound
  $3.7177 using 2000 output tokens per call), so a long-output run cannot stop before three
  drafts and the setup D run exist. The only paid call so far is the cost-check sample
  (fundamentals.revenue, $0.021).
- Run order: draft 1, M1-M3 on draft 1, setup D on draft 1 (M4), then drafts 2 and 3, then
  M1-M3 on all drafts. Design and metrics unchanged.

## 2026-10-29 (before any drafting; decisions PREREG.md does not cover)
- The tagger's reply is parsed as JSON after removing a surrounding ```json code fence, and
  nothing else is repaired. A reply that still does not parse leaves the entry with id, table and
  filter only, so it fails M3. If the model returns id, table or filter, the packet's values
  replace them.
- Tagger calls use max_tokens 2000; a reply cut off at that limit is recorded in the draft's
  parse notes.
- The questions listed next to a dangerous error (M2) are the questions whose hand-tag setup D
  runs (eval/results/D.jsonl) named that tag id in a tool call (metric_id, or get_metric's
  metric). eval/questions.yaml has no tag field to map from.
- M3 lists every failure by validating each entry on its own when load_tags fails (load_tags
  stops at the first bad entry), and runs check_tags_against_db on the entries that validated.
