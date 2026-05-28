from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urljoin

sys.path.append(str(Path(__file__).resolve().parents[1]))

from browser.playwright_context import browser_context, visible_text, wait_for_human_if_needed  # noqa: E402
from browser.screenshots import save_page_screenshot  # noqa: E402
from config import get_settings, inspect_path, screenshot_path  # noqa: E402


PIPELINE_PATHS = ["/leads/pipeline/", "/leads/", "/stats/"]


def main() -> None:
    settings = get_settings()
    if not settings.kommo_login_url:
        raise SystemExit("Falta KOMMO_LOGIN_URL.")

    evidence = []
    with browser_context("kommo") as (_, _, _, page):
        page.goto(settings.kommo_login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        wait_for_human_if_needed(page, "Kommo pipeline")

        base_url = page.url
        for path in PIPELINE_PATHS:
            candidate = urljoin(base_url, path)
            try:
                page.goto(candidate, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                evidence.append(f"\n\n## URL: {page.url}\n\n{visible_text(page, limit=12000)}")
                save_page_screenshot(page, screenshot_path(f"kommo_pipeline_{path.strip('/').replace('/', '_') or 'root'}.png"))
            except Exception as exc:
                evidence.append(f"\n\n## URL intentada: {candidate}\n\nERROR: {exc}")

        inspect_path("kommo_pipeline.txt").write_text("\n".join(evidence), encoding="utf-8")
        print("[inspect] evidencia pipeline guardada")


if __name__ == "__main__":
    main()
