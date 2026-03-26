"""Minimal page helpers for the Mercado Libre login smoke."""

from playwright.sync_api import Error, Page

from .config import HOME_URL, NAVIGATION_TIMEOUT_MS
from .selectors import LOGIN_ENTRY_SELECTORS


def _is_selector_visible(page: Page, selector: str) -> bool:
    """Return True when a selector is currently visible."""
    try:
        locator = page.locator(selector)
        return locator.count() > 0 and locator.first.is_visible()
    except Error:
        return False


def open_home(page: Page) -> None:
    """Open Mercado Libre home."""
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)


def open_login_if_needed(page: Page) -> bool:
    """Click a visible login entry-point when one is available."""
    for selector in LOGIN_ENTRY_SELECTORS:
        if not _is_selector_visible(page, selector):
            continue
        try:
            page.locator(selector).first.click()
            page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        except Error:
            return False
        return True
    return False
