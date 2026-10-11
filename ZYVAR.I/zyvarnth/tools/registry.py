from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


class ApprovalRequired(PermissionError):
    def __init__(self, tool_name: str, summary: str) -> None:
        super().__init__(summary)
        self.tool_name = tool_name
        self.summary = summary


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, tuple[type, bool]]
    handler: Callable[..., Any]
    requires_confirmation: bool = False
    reversible: bool = False


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if not spec.name.replace("_", "").isalnum() or spec.name in self._tools:
            raise ValueError("Tool names must be unique identifiers.")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def all(self) -> list[ToolSpec]:
        return list(self._tools.values())

