# PR 19 review

Reviewed with coding assistance on October 28, 2026. This records source, numerical and programmatic DOM checks. It is not Karan Patel's personal laptop/phone visual sign-off. No PR watcher was configured and no merge was performed.

## Resolved

- Recomputed the corrected scores in memory for all 504 stored runs. The complete result equals `eval/results/summary.json`, including the scorer disclosure; no result files were rewritten.
- Compared the page's accuracy counts, percentages, range labels and bar/range coordinates with the summary. Correct counts: A 122/126, B 126/126, C 124/126, D 124/126. Run ranges: A 92.9–100.0%, B 100.0–100.0%, C 97.6–100.0%, D 95.2–100.0%.
- Over-warning: A 34/102 (33.3%), B 9/102 (8.8%), C 19/102 (18.6%), D 7/102 (6.9%). The page identifies this as secondary and does not count extra warnings as incorrect answers.
- Scorer correction: 12 runs, B 8 and C 4, q022–q024. Majority-vote comparison: 41 of 42 questions agree; q010 is the only difference. Replaced the unsupported inference that the difference is "within noise" with the statement that this small sample establishes no better format and no significance test was performed.
- q017: the selected A run is run 2, FINAL 13,210,900,000 USD, with the `used_fy_value` badge and its 2-of-3 record. D shows 3,718,800,000 USD. Darden's linked FY2026 10-K reports 13,210.9 million sales, and the linked Q3 10-Q reports 9,492.1 million for the current nine-month column.
- q030 and q034 retain D's failures. Their explanations now disclose the successful workaround in D's other runs: composing quarterly requests for annual views, and retrieving company comps through a multi-company warning envelope. These are not claims that D has no possible answer path.
- Read sections 1, 2 and 5 against the data. The Yum illustration says that no recorded setup fell for that trap. The actual failure replay is q017, with q010 showing a missing caveat rather than wrong margin arithmetic. No claims that tags "fix", "improve" or "outperform" appear in those sections.
- The replay heading now counts six questions, rather than calling the displayed question/setup combinations six runs.
- Added `docs/error_analysis.md`, rebuilt the page and verified its relative link resolves to the existing local file. The "not written yet" message is gone. The analysis explicitly reports no scored B failures and distinguishes B's over-warning examples from incorrect answers.
- Labelled the page date `(UTC)`. Recorded start timestamps span 2026-10-28 00:17:40–00:25:49 UTC, which is October 27, 20:17:40–20:25:49 America/New_York. These are starts, not completion timestamps.
- README records the October 24 initial draft (`f4f35b4`) and October 27 freeze target (`88506ef`), with the lightweight-tag timestamp limitation. It also discloses the four replacement questions written after the core logic existed.
- README limitations give the exact financial window: fiscal 2024–2025 for CMG, WING and YUM; fiscal 2025–2026 for Darden.

## Filing destinations checked

The six distinct SEC links on the rebuilt page were opened and matched to their company and filing/release. Archive-folder links now point directly to the corresponding filing index. The main HTML reports were also opened; the SEC's inline viewer itself requires JavaScript.

| Accession | Destination | Period |
| --- | --- | --- |
| 0001041061-26-000084 | Yum! Brands 10-K | December 31, 2025 |
| 0001058090-26-000009 | Chipotle 10-K | December 31, 2025 |
| 0000940944-26-000025 | Darden 10-K | May 31, 2026 |
| 0000940944-26-000009 | Darden 10-Q | February 22, 2026 |
| 0001058090-26-000007 | Chipotle Exhibit 99.1 | Q4 ended December 31, 2025 |
| 0001636222-26-000006 | Wingstop Exhibit 99.1 | Q4 ended December 27, 2025 |

## Acceptance evidence

- `python -m pytest -q`: 59 passed.
- `python report/build_report.py`: completed without missing inputs or replay-score mismatches.
- Programmatic DOM checks: all six question selectors and all three A/B/C tabs (18 combinations), q017's values and badge, both D failure badges, all four summary rows, accuracy bar/range coordinates, the paired comparison, scorer disclosure, UTC label, local error-analysis link and theme toggle passed. No DOM JavaScript errors or external script/stylesheet declarations were found. A DOM check does not measure layout or visual appearance.
- Compared 19 protected question, tag, tool, scorer, verification and result files byte-for-byte with the reviewed PR head `93e2cd4`: unchanged.
- `git diff --check`: clean.

## Still pending before visual sign-off

- Open `docs/index.html` at laptop width and on a real phone, and check wrapping, horizontal scrolling, theme contrast and controls. The attempted local browser launch failed with SIGABRT; no rendered screenshots or physical-phone check were obtained. The responsive CSS was inspected, but visual acceptance remains pending.
- GitHub's file endpoint confirms the HTML exists on the PR branch. The GitHub file view could not be loaded through the available web reader, so GitHub rendering was not verified. A source-code view is not an HTML preview.
- Karan Patel should read the assisted error-analysis draft before attributing it as his own analysis or approving the page.
