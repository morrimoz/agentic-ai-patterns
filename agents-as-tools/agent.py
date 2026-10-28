"""Schema-bearing tools, isolated specialist context and one shared execution budget."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class Budget:
    max_calls: int = 20
    max_seconds: float = 30
    max_observation_chars: int = 24000
    calls: int = 0
    tool_calls: int = 0
    started: float = 0

    def consume(self):
        if not self.started:
            self.started = time.monotonic()
        if self.calls >= self.max_calls or time.monotonic() - self.started > self.max_seconds:
            raise BudgetExceeded("Shared agent execution budget exhausted")
        self.calls += 1


@dataclass
class Tool:
    name: str
    description: str
    schema: type[BaseModel]
    execute: Callable

    def descriptor(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema.model_json_schema(),
        }

    def call(self, arguments):
        parsed = self.schema.model_validate(arguments)
        return self.execute(parsed)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str | None
    arguments: dict = Field(default_factory=dict)
    answer: dict | None = None


class Agent:
    def __init__(self, model, tools, budget=None, observe=None):
        self.model = model
        self.tools = {tool.name: tool for tool in tools}
        if len(self.tools) != len(tools):
            raise ValueError("Duplicate tool names")
        self.budget = budget or Budget()
        self.observe = observe or (lambda kind, body: None)

    def run(self, objective, context):
        import json

        observations = []
        initial_calls = self.budget.calls
        initial_tools = self.budget.tool_calls
        for _ in range(self.budget.max_calls):
            self.budget.consume()
            payload = {
                "objective": objective,
                "context": context,
                "tools": [t.descriptor() for t in self.tools.values()],
                "observations": observations,
            }
            started = time.monotonic()
            raw = self.model.complete("agent", payload)
            self.observe(
                "model.called",
                {"task": "agent", "call": self.budget.calls, "seconds": round(time.monotonic() - started, 4)},
            )
            decision = Decision.model_validate(raw)
            if decision.tool is None:
                if not observations or decision.answer is None:
                    raise ValueError("Specialist cannot finish without observations and a structured answer")
                return {
                    "answer": decision.answer,
                    "observations": observations,
                    "model_calls": self.budget.calls - initial_calls,
                    "tool_calls": self.budget.tool_calls - initial_tools,
                }
            if decision.tool not in self.tools:
                raise ValueError("Unregistered tool selected")
            result = self.tools[decision.tool].call(decision.arguments)
            rendered = json.dumps(result, default=str)
            if len(rendered) > self.budget.max_observation_chars:
                raise BudgetExceeded("Tool result exceeds observation budget; use a paged tool")
            self.budget.tool_calls += 1
            observations.append({"tool": decision.tool, "arguments": decision.arguments, "result": result})
            self.observe(
                "tool.executed",
                {"tool": decision.tool, "arguments": decision.arguments, "result_chars": len(rendered)},
            )
        raise BudgetExceeded("Agent did not finish")
