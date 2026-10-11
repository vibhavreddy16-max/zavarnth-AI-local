from __future__ import annotations

from typing import Any

from ..security import validate_http_url


class BrowserController:
    """Isolated Playwright navigation and visible-text extraction."""

    def visit(self, url: str) -> dict[str, Any]:
        safe_url = validate_http_url(url)
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError("Install Zyvarnth's declared Playwright dependency first.") from exc
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(safe_url, wait_until="domcontentloaded", timeout=20000)
                title = page.title()
                text = page.locator("body").inner_text(timeout=8000)[:12000]
                final_url = page.url
                browser.close()
        except Exception as exc:
            message = str(exc).splitlines()[0][:240]
            raise RuntimeError(f"Browser visit failed: {message}") from exc
        return {"title": title, "url": final_url, "text": text}

    def interact(self, url: str, action: str, selector: str, value: str = "") -> dict[str, Any]:
        safe_url = validate_http_url(url)
        if action not in {"click", "fill"}:
            raise ValueError("Browser action must be click or fill.")
        if not selector.strip() or len(selector) > 240:
            raise ValueError("Provide one CSS or text selector up to 240 characters.")
        if action == "fill" and (len(value) > 3000):
            raise ValueError("Browser form input is limited to 3,000 characters.")
        from playwright.sync_api import sync_playwright

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(safe_url, wait_until="domcontentloaded", timeout=20000)
                target = page.locator(selector)
                count = target.count()
                if count != 1 or not target.is_visible():
                    raise RuntimeError(f"Selector matched {count} visible elements; exactly one is required.")
                if action == "fill":
                    target.fill(value, timeout=5000)
                else:
                    target.click(timeout=5000)
                    try:
                        page.wait_for_load_state("domcontentloaded", timeout=5000)
                    except Exception:
                        pass
                result = {"title": page.title(), "url": page.url, "text": page.locator("body").inner_text(timeout=5000)[:8000]}
                browser.close()
                return result
        except Exception as exc:
            message = str(exc).splitlines()[0][:220]
            raise RuntimeError(f"Browser interaction failed: {message}") from exc

