"""Minimal actions for the Mercado Libre login smoke."""

import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page

from .config import LOGIN_POLL_INTERVAL_SEC
from .selectors import (
    ACCOUNT_MENU_SELECTORS,
    ACCOUNT_URL_HINTS,
    LOGIN_ENTRY_SELECTORS,
    LOGIN_URL_HINTS,
    SESSION_COOKIE_NAMES,
)


def _is_selector_visible(page: Page, selector: str) -> bool:
    """Return True when a selector is currently visible."""
    try:
        locator = page.locator(selector)
        return locator.count() > 0 and locator.first.is_visible()
    except Error:
        return False


def _any_visible(page: Page, selectors: list[str]) -> bool:
    """Return True when any selector from the list is visible."""
    return any(_is_selector_visible(page, selector) for selector in selectors)


def _url_has_hint(page: Page, hints: tuple[str, ...]) -> bool:
    """Return True when the current URL contains a known hint."""
    url = page.url.lower()
    return any(hint in url for hint in hints)


def _has_session_cookie(context: BrowserContext) -> bool:
    """Check for common auth-cookie names as a weak fallback."""
    try:
        cookies = context.cookies()
    except Error:
        return False
    return any(cookie.get("name") in SESSION_COOKIE_NAMES for cookie in cookies)


def has_login_prompt(page: Page) -> bool:
    """Check whether the page still exposes a login prompt."""
    return _any_visible(page, LOGIN_ENTRY_SELECTORS) or _url_has_hint(page, LOGIN_URL_HINTS)


def is_logged_in(page: Page) -> bool:
    """Check whether the session appears to be authenticated."""
    if _any_visible(page, ACCOUNT_MENU_SELECTORS) or _url_has_hint(page, ACCOUNT_URL_HINTS):
        return True
    if has_login_prompt(page):
        return False
    return _has_session_cookie(page.context)


def wait_for_manual_login(page: Page, timeout_sec: int = 180) -> bool:
    """Poll the page while the user completes manual login."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if page.is_closed():
            return False
        if is_logged_in(page):
            return True
        page.wait_for_timeout(LOGIN_POLL_INTERVAL_SEC * 1000)
    return is_logged_in(page)


def save_debug_screenshot(page: Page, path: Path) -> None:
    """Save a basic screenshot for manual inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=False)


def maybe_save_storage_state(context: BrowserContext, path: Path) -> None:
    """Save storage state for reuse in later runs."""
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
