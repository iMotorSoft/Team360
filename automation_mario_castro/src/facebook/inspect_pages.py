from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from browser.playwright_context import browser_context, visible_text, wait_for_human_if_needed  # noqa: E402
from browser.screenshots import save_page_screenshot  # noqa: E402
from config import inspect_path, screenshot_path  # noqa: E402


PAGES = [
    "https://www.facebook.com/Mariocastroremax",
    "https://www.facebook.com/profile.php?id=100090112818347",
]


def main() -> None:
    evidence = []
    with browser_context("facebook") as (_, _, _, page):
        for index, url in enumerate(PAGES, start=1):
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)
            wait_for_human_if_needed(page, f"Facebook page {index}")
            text = visible_text(page, limit=14000)
            evidence.append(f"\n\n## Page {index}: {url}\nFinal URL: {page.url}\n\n{text}")
            save_page_screenshot(page, screenshot_path(f"facebook_page_{index}.png"))

        inspect_path("facebook_pages.txt").write_text("\n".join(evidence), encoding="utf-8")
        print("[inspect] evidencia paginas Facebook guardada")


if __name__ == "__main__":
    main()
