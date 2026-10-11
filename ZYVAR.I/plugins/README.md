# Local Zyvarnth plugins

Each top-level `*.py` module can define `register() -> list[ToolSpec]`. New plugin modules appear in Settings and remain disabled until checked. Enabling one means trusting its Python code; it runs with the application user's privileges after the next restart.

The example [`local_clock.py`](local_clock.py) has no side effects and shows a typed argument declaration. `ToolExecutor` validates declared argument types and logs results. A plugin must set `requires_confirmation=True` for consequential operations and should validate argument content inside its handler. It cannot obtain arbitrary shell access through Zyvarnth's built-in tool layer.

