from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from browser.playwright_context import browser_context, visible_text, wait_for_human_if_needed  # noqa: E402
from browser.screenshots import save_page_screenshot  # noqa: E402
from config import inspect_path, screenshot_path  # noqa: E402


INBOX_URLS = [
    "https://business.facebook.com/latest/inbox/all",
    "https://business.facebook.com/latest/inbox",
]


def main() -> None:
    evidence = []
    with browser_context("facebook") as (_, _, _, page):
        for index, url in enumerate(INBOX_URLS, start=1):
            try:
                page.goto(url, wait_until="domcontentloaded")
                page.wait_for_timeout(7000)
                wait_for_human_if_needed(page, f"Meta inbox {index}")
                evidence.append(f"\n\n## Inbox URL {index}: {url}\nFinal URL: {page.url}\n\n{visible_text(page, limit=16000)}")
                save_page_screenshot(page, screenshot_path(f"facebook_inbox_{index}.png"))
            except Exception as exc:
                evidence.append(f"\n\n## Inbox URL {index}: {url}\nERROR: {exc}")

        inspect_path("facebook_inbox.txt").write_text("\n".join(evidence), encoding="utf-8")
        print("[inspect] evidencia Inbox guardada")


if __name__ == "__main__":
    main()
