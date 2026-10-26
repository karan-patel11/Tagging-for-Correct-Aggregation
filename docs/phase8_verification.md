# Phase 8 local MCP verification

Date: 2026-10-26. PR: #12, branch `claude/festive-ritchie-b6fdlj`.
Server implementation checked at commit `1907c506afa51325c3366480b361cb7afb3fd3a7`.

## Environment and acceptance checks

- Python 3.13.12; MCP SDK 2.3.0. Project minimum: Python 3.11.
- Dependency bound: `mcp>=2.3,<3`, retaining the tested major-version API.
- The supplied local Terminal output records database checks D1–D9 passing and 34 tests passing in 1.92 seconds.
- Claude Code registration uses the absolute virtual-environment Python and absolute `src/mcp_server.py` path. The supplied `claude mcp list` output reports Connected.
- The supplied `/mcp` output lists exactly four tools: `list_metrics`, `describe_column`, `get_metric`, `aggregate`.

## Live Claude Code demo

The user supplied a local Claude Code transcript requesting `describe_column` for `fundamentals.op_cash_flow`, followed by `get_metric` for ticker `DRI`, metric `op_cash_flow`, period `FY2025Q3`.

The transcript reports two calls to restaurant-semantics and returns **588,200,000 USD**, for **2024-11-25 through 2025-02-23**, with two SEC sources. Its copied output contains line-wrap artifacts; the protocol check below records the unwrapped result. The collapsed transcript does not expose the individual call names or arguments, so those are independently checked through the protocol below rather than inferred from the collapsed call counter.

## Independent stdio protocol check

A real `mcp.Client` launched the virtual-environment Python with the absolute server path using `StdioServerParameters(cwd="/tmp")`. This exercises the subprocess stdio transport and database resolution outside the repository working directory; it is separate from the in-process MCP unit tests.

- `list_tools` returned exactly `list_metrics`, `describe_column`, `get_metric`, `aggregate`.
- `describe_column({"metric_id":"fundamentals.op_cash_flow"})` returned status `ok`.
- `get_metric({"ticker":"DRI","metric":"op_cash_flow","period":"FY2025Q3"})` returned status `ok`, value `588200000.0`, unit `USD`, start `2024-11-25`, end `2025-02-23`.
- Derivation: `YTD9 = 1250000000.0`; `YTD6 = 661800000.0`; `Q3 = YTD9 - YTD6 = 588200000.0`.
- Both cumulative pieces start `2024-05-27`. The earlier piece ends `2024-11-24`, the day before the derived quarter starts.
- Source accessions are exactly `0000940944-26-000009` (YTD9) and `0000940944-25-000071` (YTD6).

This checks the existing expected value; it does not generate or change the independent answer key.

## Primary-source checks

Both filing indexes and main 10-Q documents were opened for this verification. These are the latest-filed comparative facts selected by the warehouse's duration deduplication rule.

| Piece | Filing and date | Comparative period | Row and scale | Value |
|---|---|---|---|---:|
| YTD9 | [10-Q index, 0000940944-26-000009](https://www.sec.gov/Archives/edgar/data/940944/000094094426000009/0000940944-26-000009-index.htm), filed 2026-03-27; [main document](https://www.sec.gov/Archives/edgar/data/940944/000094094426000009/dri-20260222.htm) | Prior-year nine months ended 2025-02-23 | Net cash provided by operating activities of continuing operations; millions of USD | 1,250.0 |
| YTD6 | [10-Q index, 0000940944-25-000071](https://www.sec.gov/Archives/edgar/data/940944/000094094425000071/0000940944-25-000071-index.htm), filed 2025-12-30; [main document](https://www.sec.gov/Archives/edgar/data/940944/000094094425000071/dri-20251123.htm) | Prior-year six months ended 2024-11-24 | Net cash provided by operating activities of continuing operations; millions of USD | 661.8 |

Current-year amounts 1,281.0 and 663.2 are excluded. The resulting quarter is continuing operations only; discontinued operations are excluded.

## Follow-up validation

After the dependency-bound and documentation changes, `python -m pytest -q` completed with **34 passed in 1.62 seconds**. `git diff --check` passed. The installed MCP SDK is 2.3.0, within the required `>=2.3,<3` bound.

Merge is a separate step after the verification changes have been committed and pushed to PR #12.
