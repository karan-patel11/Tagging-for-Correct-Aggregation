"""Phase 8 tests: the MCP server is four thin wrappers over semantics.py (SPEC §10)."""
import json
import re
from pathlib import Path

import anyio
import mcp_server
import semantics
from mcp import Client
from tool_specs import DESCRIPTIONS, TOOL_NAMES

SPEC = Path(__file__).resolve().parent.parent / "SPEC.md"


def _call_via_protocol(name, arguments):
    """Call a tool through a real MCP client connected in-process to the server."""
    async def go():
        async with Client(mcp_server.server) as client:
            return await client.call_tool(name, arguments)
    result = anyio.run(go)
    return json.loads(result.content[0].text)


def test_exactly_four_tools_with_spec_descriptions():
    async def go():
        async with Client(mcp_server.server) as client:
            return (await client.list_tools()).tools
    tools = anyio.run(go)
    assert [t.name for t in tools] == ["list_metrics", "describe_column", "get_metric", "aggregate"]
    assert {t.name: t.description for t in tools} == DESCRIPTIONS
    assert TOOL_NAMES == [t.name for t in tools]


def test_descriptions_match_spec_section_10_word_for_word():
    text = SPEC.read_text()
    section = text[text.index("## 10. MCP server specification"):text.index("## 11.")]
    for name, description in DESCRIPTIONS.items():
        assert f'- `{name}`: "{description}"' in section


def test_get_metric_matches_semantics_with_two_sources():
    args = {"ticker": "DRI", "metric": "op_cash_flow", "period": "FY2025Q3"}
    expected = json.loads(json.dumps(semantics.get_metric(**args)))
    assert mcp_server.call_tool("get_metric", args) == expected
    assert _call_via_protocol("get_metric", args) == expected
    assert expected["status"] == "ok"
    assert len(expected["sources"]) == 2


def test_all_tools_return_the_semantics_envelope_unchanged():
    cases = {
        "list_metrics": {},
        "describe_column": {"metric_id": "fundamentals.total_assets"},
        "aggregate": {"metric_id": "fundamentals.total_assets", "entities": ["YUM"],
                      "period": "FY2025", "method": "last"},
    }
    for name, args in cases.items():
        expected = json.loads(json.dumps(getattr(semantics, name)(**args)))
        assert mcp_server.call_tool(name, args) == expected


def test_disallowed_method_returns_error_with_use_instead():
    env = _call_via_protocol("aggregate", {"metric_id": "fundamentals.total_assets", "entities": ["YUM"],
                                           "period": "FY2025", "method": "sum_over_time"})
    assert env["status"] == "error"
    assert env["use_instead"] == "last"


def test_unknown_metric_returns_error_envelope_not_exception():
    for name, args in [("describe_column", {"metric_id": "nope"}),
                       ("get_metric", {"ticker": "DRI", "metric": "nope", "period": "FY2025"}),
                       ("aggregate", {"metric_id": "nope", "entities": ["YUM"], "period": "FY2025",
                                      "method": "last"})]:
        env = mcp_server.call_tool(name, args)
        assert env["status"] == "error"
        assert "nope" in env["explanation"]
        assert _call_via_protocol(name, args)["status"] == "error"


def test_bad_input_never_crashes_the_server():
    bad = [("get_metric", {"ticker": "DRI"}),                      # missing arguments
           ("get_metric", {"ticker": "DRI", "metric": "op_cash_flow", "period": "FY2025Q3", "x": 1}),
           ("aggregate", {"metric_id": "fundamentals.total_assets", "entities": None,
                          "period": "FY2025", "method": "last"}),
           ("no_such_tool", {})]
    for name, args in bad:
        env = _call_via_protocol(name, args)
        assert env["status"] == "error"
        assert env["explanation"]
    # The same server connection keeps working afterwards.
    assert _call_via_protocol("list_metrics", {})["status"] == "ok"


def test_tool_specs_imports_no_mcp_sdk():
    source = (Path(mcp_server.__file__).parent / "tool_specs.py").read_text()
    assert not re.search(r"^\s*(import|from)\s+(mcp|mcp_types)\b", source, re.M)
