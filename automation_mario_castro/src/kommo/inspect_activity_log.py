from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.append(str(Path(__file__).resolve().parents[1]))

from browser.playwright_context import browser_context, visible_text, wait_for_human_if_needed  # noqa: E402
from browser.screenshots import save_page_screenshot  # noqa: E402
from config import get_settings, inspect_path, screenshot_path  # noqa: E402


ACTIVITY_PATHS = ["/events/list/", "/stats/events/list/", "/analytics/events/list/"]


def extract_visible_table_rows(page) -> list[dict]:
    rows = []
    row_locators = page.locator("table tbody tr, [role='row']")
    try:
        count = min(row_locators.count(), 100)
    except Exception:
        return rows

    for index in range(count):
        row = row_locators.nth(index)
        try:
            text = row.inner_text(timeout=2000).strip()
        except Exception:
            continue
        if not text:
            continue
        rows.append({"index": index, "text": text})
    return rows


def main() -> None:
    settings = get_settings()
    if not settings.kommo_login_url:
        raise SystemExit("Falta KOMMO_LOGIN_URL.")

    evidence = []
    structured = []
    with browser_context("kommo") as (_, _, _, page):
        page.goto(settings.kommo_login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        wait_for_human_if_needed(page, "Kommo activity log")

        base_url = page.url
        for path in ACTIVITY_PATHS:
            candidate = urljoin(base_url, path)
            try:
                page.goto(candidate, wait_until="domcontentloaded")
                page.wait_for_timeout(5000)
                wait_for_human_if_needed(page, f"Kommo activity log {path}")
                text = visible_text(page, limit=20000)
                rows = extract_visible_table_rows(page)
                evidence.append(f"\n\n## URL: {page.url}\n\n{text}")
                structured.append({"url": page.url, "rows": rows})
                save_page_screenshot(page, screenshot_path(f"kommo_activity_log_{path.strip('/').replace('/', '_') or 'root'}.png"))
            except Exception as exc:
                evidence.append(f"\n\n## URL intentada: {candidate}\n\nERROR: {exc}")
                structured.append({"url": candidate, "error": str(exc), "rows": []})

        inspect_path("kommo_activity_log.txt").write_text("\n".join(evidence), encoding="utf-8")
        inspect_path("kommo_activity_log_rows.json").write_text(
            json.dumps(structured, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("[inspect] evidencia Registro de actividades guardada")


if __name__ == "__main__":
    main()
