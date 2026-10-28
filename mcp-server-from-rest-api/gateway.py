"""Synchronous graph callers use a managed async MCP client on a dedicated event loop."""

import json
import sys
from contextlib import AsyncExitStack, asynccontextmanager

from anyio.from_thread import start_blocking_portal
from jsonschema import Draft202012Validator
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class Gateway:
    def __init__(self, path, tenant):
        self.path, self.tenant = str(path), tenant

    @asynccontextmanager
    async def _session(self):
        async with AsyncExitStack() as stack:
            await self._initialize(stack)
            yield self.session

    async def _initialize(self, stack):
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "patterns.mcp_bridge.server", "--db", self.path, "--tenant", self.tenant],
        )
        streams = await stack.enter_async_context(stdio_client(parameters))
        self.session = await stack.enter_async_context(ClientSession(*streams))
        await self.session.initialize()
        self.discovered = {tool.name: tool for tool in (await self.session.list_tools()).tools}

    def __enter__(self):
        self.portal_context = start_blocking_portal()
        self.portal = self.portal_context.__enter__()
        try:
            self.session_context = self.portal.wrap_async_context_manager(self._session())
            self.session_context.__enter__()
        except BaseException:
            self.portal_context.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *args):
        try:
            self.session_context.__exit__(*args)
        finally:
            self.portal_context.__exit__(*args)

    def tools(self):
        return [tool.model_dump() for tool in self.discovered.values()]

    async def _call(self, name, args):
        response = await self.session.call_tool(name, args)
        if response.isError:
            raise ValueError(
                "Accounting tool failed: " + "".join(getattr(item, "text", "") for item in response.content)
            )
        return json.loads(response.content[0].text)

    def call(self, name, args):
        if name not in self.discovered:
            raise ValueError("Tool is not available in this MCP session")
        Draft202012Validator(self.discovered[name].inputSchema).validate(args)
        return self.portal.call(self._call, name, args)
