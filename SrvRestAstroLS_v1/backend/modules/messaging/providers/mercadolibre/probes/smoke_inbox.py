"""Smoke probe for Mercado Libre inbox access and basic visibility."""

import argparse
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page, sync_playwright

from ..browser.actions import (
    can_access_inbox,
    count_visible_threads,
    get_current_url,
    get_page_title,
    inbox_empty_state,
    is_logged_in,
    maybe_save_storage_state,
    save_debug_screenshot,
)
from ..browser.config import DEFAULT_PROFILE_NAME
from ..browser.context import close_context, open_persistent_context
from ..browser.pages import ensure_inbox_loaded, maybe_open_inbox_candidates, stabilize_inbox
from ..browser.session_store import get_screenshot_path, get_storage_state_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Inbox smoke for Mercado Libre persistent browser sessions.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME, help="Persistent browser profile name.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait for inbox load signals.")
    return parser.parse_args()


def log(message: str) -> None:
    """Print a short progress message."""
    print(message, flush=True)


def _save_artifacts(
    page: Page | None,
    context: BrowserContext | None,
    screenshot_path: Path,
    storage_state_path: Path,
) -> None:
    """Persist a screenshot and storage state when possible."""
    if page is not None and not page.is_closed():
        try:
            save_debug_screenshot(page, screenshot_path)
            log(f"screenshot guardado en {screenshot_path}")
        except Error as exc:
            log(f"no se pudo guardar screenshot: {exc}")
    if context is not None:
        try:
            maybe_save_storage_state(context, storage_state_path)
            log(f"storage state guardado en {storage_state_path}")
        except Error as exc:
            log(f"no se pudo guardar storage state: {exc}")


def run(profile_name: str, timeout_sec: int) -> int:
    """Execute the inbox smoke flow."""
    screenshot_path = get_screenshot_path(prefix=f"smoke_inbox_{profile_name}")
    storage_state_path = get_storage_state_path(profile_name)

    context: BrowserContext | None = None
    page: Page | None = None
    logged_in = False
    inbox_accessible = False
    visible_threads = 0
    empty_state = False
    final_url = ""
    page_title = ""

    log("iniciando browser persistente")
    log(f"profile usado: {profile_name}")

    with sync_playwright() as playwright:
        try:
            context, page = open_persistent_context(playwright, profile_name=profile_name)
            log("abriendo inbox Mercado Libre")
            maybe_open_inbox_candidates(page, timeout_ms=max(timeout_sec, 1) * 1000)
            ensure_inbox_loaded(page, timeout_ms=2_000)
            stabilize_inbox(page)

            logged_in = is_logged_in(page)
            log("sesion activa" if logged_in else "login requerido")

            inbox_accessible = can_access_inbox(page)
            log("inbox accesible" if inbox_accessible else "inbox no accesible")

            visible_threads = count_visible_threads(page)
            empty_state = inbox_empty_state(page)
            final_url = get_current_url(page)
            page_title = get_page_title(page)

            log(f"final url {final_url}")
            log(f"page title {page_title}")
            log(f"hilos visibles detectados: {visible_threads}")
            log(f"empty state detectado: {empty_state}")
        except Error as exc:
            log(f"error durante smoke inbox: {exc}")
        finally:
            _save_artifacts(page, context, screenshot_path, storage_state_path)
            close_context(context)

    log(f"inbox_accessible {inbox_accessible}")
    log(f"visible_threads {visible_threads}")
    log(f"empty_state {empty_state}")
    log(f"final_url {final_url}")
    log(f"page_title {page_title}")
    log(f"screenshot path {screenshot_path}")
    log("fin")
    return 0 if logged_in and inbox_accessible else 1


def main() -> int:
    """Run the probe from the command line."""
    args = parse_args()
    return run(profile_name=args.profile, timeout_sec=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
