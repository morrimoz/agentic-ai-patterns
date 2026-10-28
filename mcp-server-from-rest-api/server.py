"""MCP stdio server. Write capabilities are selected by the trusted execution boundary."""

import argparse
import asyncio
import json

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from .compiler import Compiler
from .erp import ERPClient, create_erp_app


def build_server(path, tenant, allow_write=False):
    compiler = Compiler(create_erp_app(path).openapi())
    client = ERPClient(path)
    server = Server("accounting-sandbox")

    @server.list_tools()
    async def tools():
        return [
            tool for tool in compiler.tools() if allow_write or compiler.by_name[tool.name].effect == "read"
        ]

    @server.call_tool()
    async def call(name: str, arguments: dict):
        operation, url, query, body = compiler.request(name, arguments)
        if operation.effect != "read" and not allow_write:
            raise ValueError("Write tool unavailable in this session")
        # The public read-only agent session never receives write credentials or headers.
        result = await asyncio.to_thread(
            client.request, tenant, operation.method, url, params=query, json=body
        )
        return [TextContent(type="text", text=json.dumps(result))]

    return server


async def serve(path, tenant):
    server = build_server(path, tenant)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--tenant", required=True)
    args = parser.parse_args()
    asyncio.run(serve(args.db, args.tenant))
