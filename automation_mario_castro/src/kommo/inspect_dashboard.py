from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from browser.playwright_context import browser_context, wait_for_human_if_needed, write_visible_text  # noqa: E402
from browser.screenshots import save_page_screenshot  # noqa: E402
from config import get_settings, inspect_path, screenshot_path  # noqa: E402


def main() -> None:
    settings = get_settings()
    if not settings.kommo_login_url:
        raise SystemExit("Falta KOMMO_LOGIN_URL.")

    with browser_context("kommo") as (_, _, _, page):
        page.goto(settings.kommo_login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        wait_for_human_if_needed(page, "Kommo dashboard")
        save_page_screenshot(page, screenshot_path("kommo_dashboard.png"))
        write_visible_text(page, inspect_path("kommo_dashboard.txt"))
        print(f"[inspect] URL final: {page.url}")


if __name__ == "__main__":
    main()
