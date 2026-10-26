"""Phase 8: MCP server (SPEC §10). Four thin wrappers around semantics.py over stdio.

Each tool calls the matching semantics.py function and returns its §9.2 envelope unchanged, as JSON.
No aggregation logic, period parsing or validation lives here: names, descriptions and schemas come
from tool_specs.py, and any exception from semantics.py becomes a status "error" envelope.

Stdout carries only MCP protocol messages; logs go to stderr.

Run: python src/mcp_server.py
"""
import json
import logging
import sys

import anyio
import mcp_types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

import semantics
from tool_specs import TOOL_SPECS

logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("restaurant-semantics")

FUNCTIONS = {name: getattr(semantics, name) for name in ("list_metrics", "describe_column", "get_metric", "aggregate")}


def call_tool(name, arguments=None):
    """Run one tool and return its envelope (a dict). Never raises."""
    try:
        if name not in FUNCTIONS:
            return semantics._error(f"unknown tool '{name}'; tools are {sorted(FUNCTIONS)}")
        return FUNCTIONS[name](**(arguments or {}))
    except Exception as e:
        log.exception("tool %s failed", name)
        return semantics._error(f"{type(e).__name__}: {e}")


def list_tools():
    return [types.Tool(name=t["name"], description=t["description"], inputSchema=t["input_schema"])
            for t in TOOL_SPECS]


async def _on_list_tools(ctx, params):
    return types.ListToolsResult(tools=list_tools())


async def _on_call_tool(ctx, params):
    envelope = call_tool(params.name, params.arguments)
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(envelope))],
                                isError=envelope["status"] == "error")


server = Server("restaurant-semantics", on_list_tools=_on_list_tools, on_call_tool=_on_call_tool)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    log.info("starting restaurant-semantics over stdio")
    anyio.run(main)
