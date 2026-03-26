"""Persistent Playwright context helpers for the browser lab."""

from playwright.sync_api import BrowserContext, Error, Page, Playwright

from .config import DEFAULT_PROFILE_NAME, DEFAULT_TIMEOUT_MS, HEADLESS, NAVIGATION_TIMEOUT_MS
from .session_store import ensure_runtime_dirs, get_profile_dir


def open_persistent_context(
    playwright: Playwright,
    profile_name: str = DEFAULT_PROFILE_NAME,
) -> tuple[BrowserContext, Page]:
    """Open Chromium with a persistent profile and return a usable page."""
    ensure_runtime_dirs()
    profile_dir = get_profile_dir(profile_name)
    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        headless=HEADLESS,
    )
    context.set_default_timeout(DEFAULT_TIMEOUT_MS)
    context.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)
    page = context.pages[0] if context.pages else context.new_page()
    return context, page


def close_context(context: BrowserContext | None) -> None:
    """Close the browser context if it is open."""
    if context is None:
        return
    try:
        context.close()
    except Error:
        return
