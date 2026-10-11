from __future__ import annotations

from io import BytesIO


def capture_screenshot() -> bytes:
    """Capture a screenshot only when called by an explicit user action."""
    try:
        from PIL import ImageGrab

        image = ImageGrab.grab(all_screens=True)
        output = BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()
    except Exception as exc:
        detail = str(exc).splitlines()[0][:220]
        raise RuntimeError(f"Screenshot capture failed. Check this app's screen-recording permission. {detail}") from exc

