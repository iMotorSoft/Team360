"""Smoke probe for manual Mercado Libre login and session reuse."""

import argparse
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page, sync_playwright

from ..browser.actions import (
    is_logged_in,
    maybe_save_storage_state,
    save_debug_screenshot,
    wait_for_manual_login,
)
from ..browser.config import DEFAULT_PROFILE_NAME, MANUAL_LOGIN_TIMEOUT_SEC
from ..browser.context import close_context, open_persistent_context
from ..browser.pages import open_home, open_login_if_needed
from ..browser.session_store import get_screenshot_path, get_storage_state_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Manual login smoke for Mercado Libre persistent browser sessions.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME, help="Persistent browser profile name.")
    parser.add_argument("--timeout", type=int, default=MANUAL_LOGIN_TIMEOUT_SEC, help="Seconds to wait for manual login.")
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
    """Execute the smoke flow."""
    screenshot_path = get_screenshot_path(prefix=f"smoke_login_{profile_name}")
    storage_state_path = get_storage_state_path(profile_name)

    context: BrowserContext | None = None
    page: Page | None = None
    logged_in = False
    artifacts_saved = False

    log("iniciando browser persistente")
    log(f"profile usado: {profile_name}")

    with sync_playwright() as playwright:
        try:
            context, page = open_persistent_context(playwright, profile_name=profile_name)
            log("abriendo Mercado Libre")
            open_home(page)

            logged_in = is_logged_in(page)
            if logged_in:
                log("sesion activa detectada")
            else:
                log("login manual requerido")
                open_login_if_needed(page)
                log("esperando login manual")
                log("completa el login en la ventana del browser y volve a esta consola")
                logged_in = wait_for_manual_login(page, timeout_sec=timeout_sec)
                log("login validado" if logged_in else "login no validado")
        except Error as exc:
            log(f"error durante smoke login: {exc}")
        finally:
            if not artifacts_saved:
                _save_artifacts(page, context, screenshot_path, storage_state_path)
                artifacts_saved = True
            close_context(context)

    log(f"logged_in {logged_in}")
    log(f"screenshot path {screenshot_path}")
    log(f"storage state path {storage_state_path}")
    log("fin")
    return 0 if logged_in else 1


def main() -> int:
    """Run the probe from the command line."""
    args = parse_args()
    return run(profile_name=args.profile, timeout_sec=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
