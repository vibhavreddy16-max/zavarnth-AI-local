"""Optional example plugin. It is inert unless explicitly enabled in Settings."""

from datetime import datetime
from zoneinfo import ZoneInfo

from zyvarnth.tools.registry import ToolSpec


def current_time(timezone: str = "") -> dict[str, str]:
    """Return the current local time or an explicit IANA timezone."""
    zone = ZoneInfo(timezone) if timezone else datetime.now().astimezone().tzinfo
    now = datetime.now(zone)
    return {"local_time": now.isoformat(timespec="seconds"), "timezone": str(now.tzinfo)}


def register() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="get_local_time",
            description="Read the current time, optionally in an IANA timezone such as Europe/Paris.",
            parameters={"timezone": (str, False)},
            handler=current_time,
        )
    ]

