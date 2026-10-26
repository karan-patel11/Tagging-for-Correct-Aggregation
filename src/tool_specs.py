"""The four MCP tools: names, descriptions and input schemas (SPEC §10).

Single source of truth. src/mcp_server.py serves these and the evaluation's setup D (Phase 12)
imports them, so models see identical text in both. Imports nothing from the MCP SDK.

The input schemas only describe the arguments. They enforce nothing: the server does no validation
of its own, and semantics.py decides what a valid method, metric or period is.
"""

_STR = {"type": "string"}

TOOL_SPECS = [
    {
        "name": "list_metrics",
        "description": "List available metrics with one-line descriptions.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_column",
        "description": (
            "Return the semantic tags for a metric: type, how it may be aggregated, period basis, "
            "calendar, units, and lineage. Call this before computing anything."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_id": {**_STR, "description": "Metric ID from list_metrics, e.g. fundamentals.total_assets."},
            },
            "required": ["metric_id"],
        },
    },
    {
        "name": "get_metric",
        "description": (
            "Return one company's value for one period (FY2025 or FY2025Q3). Derives single quarters "
            "from year-to-date values when needed. Returns sources."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ticker": {**_STR, "description": "Company ticker: CMG, WING, YUM or DRI."},
                "metric": {**_STR, "description": "Short fundamentals metric name, e.g. op_cash_flow."},
                "period": {**_STR, "description": "Fiscal period: FY2025 or FY2025Q3."},
            },
            "required": ["ticker", "metric", "period"],
        },
    },
    {
        "name": "aggregate",
        "description": (
            "Aggregate a metric across companies or periods using a named method. Rejects methods the "
            "metric's tags don't allow and suggests the correct one. Returns sources and warnings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "metric_id": {**_STR, "description": "Metric ID from list_metrics, e.g. fundamentals.total_assets."},
                "entities": {"type": "array", "items": _STR,
                             "description": "Tickers (or brands for pageviews) to aggregate."},
                "period": {**_STR, "description": "FY2025, FY2025Q3, CY2025Q1 or 2025-01:2025-12."},
                "method": {**_STR, "description": "Aggregation method name."},
                "denominator_id": {**_STR, "description": "Denominator metric ID, only for ratio_of_sums."},
            },
            "required": ["metric_id", "entities", "period", "method"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOL_SPECS]
DESCRIPTIONS = {t["name"]: t["description"] for t in TOOL_SPECS}
