from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlparse


class SecurityError(ValueError):
    pass


def redact_sensitive_text(value: str, secret: str | None = None) -> str:
    text = value.splitlines()[0][:500]
    if secret:
        text = text.replace(secret, "[redacted]")
    return re.sub(r"AIza[0-9A-Za-z_-]{20,}", "[redacted API key]", text)


def validate_http_url(value: str) -> str:
    value = value.strip()
    if len(value) > 2048:
        raise SecurityError("URLs are limited to 2,048 characters.")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SecurityError("Only complete http:// or https:// URLs are allowed.")
    if parsed.username or parsed.password:
        raise SecurityError("URLs containing embedded credentials are not allowed.")
    return value


def approved_path(path: str | Path, roots: list[str]) -> Path:
    candidate = Path(path).expanduser().resolve(strict=False)
    for root in roots:
        base = Path(root).expanduser().resolve(strict=True)
        try:
            candidate.relative_to(base)
            return candidate
        except ValueError:
            continue
    raise SecurityError("That path is outside the folders approved in Settings.")


def safe_pattern(pattern: str) -> str:
    if not pattern or len(pattern) > 120 or ".." in pattern or "/" in pattern or "\\" in pattern:
        raise SecurityError("Use a simple filename pattern such as *.pdf or notes*.txt.")
    return pattern

