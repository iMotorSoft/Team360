"""Minimal page helpers for the Mercado Libre browser lab."""

import time

from playwright.sync_api import Error, Page

from .config import ACCOUNT_SUMMARY_URL, HOME_URL, INBOX_CANDIDATE_URLS, INBOX_URL, NAVIGATION_TIMEOUT_MS, QUESTIONS_URL
from .selectors import (
    INBOX_CONTAINER_SELECTORS,
    INBOX_DENIED_HINT_SELECTORS,
    INBOX_EMPTY_STATE_SELECTORS,
    INBOX_THREAD_SELECTORS,
    INBOX_URL_HINTS,
    LOGIN_ENTRY_SELECTORS,
)


def _is_selector_visible(page: Page, selector: str) -> bool:
    """Return True when a selector is currently visible."""
    try:
        locator = page.locator(selector)
        return locator.count() > 0 and locator.first.is_visible()
    except Error:
        return False


def _any_visible(page: Page, selectors: list[str]) -> bool:
    """Return True when any selector is currently visible."""
    return any(_is_selector_visible(page, selector) for selector in selectors)


def _url_has_hint(page: Page, hints: tuple[str, ...]) -> bool:
    """Return True when the current URL contains a known hint."""
    url = page.url.lower()
    return any(hint in url for hint in hints)


def _stabilize_page(page: Page, settle_ms: int) -> None:
    """Wait for late client-side rendering with tolerant extra settling."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=5_000)
    except Error:
        pass
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)
    except Error:
        pass
    try:
        page.evaluate("window.scrollTo(0, 400)")
        page.wait_for_timeout(500)
        page.evaluate("window.scrollTo(0, 0)")
    except Error:
        pass
    if settle_ms > 0:
        page.wait_for_timeout(settle_ms)


def open_home(page: Page) -> None:
    """Open Mercado Libre home."""
    page.goto(HOME_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)


def stabilize_home(page: Page, settle_ms: int = 3_000) -> None:
    """Wait a bit for authenticated home affordances to appear."""
    _stabilize_page(page, settle_ms=settle_ms)


def open_account_summary(page: Page) -> None:
    """Open the Mercado Libre account summary page."""
    page.goto(ACCOUNT_SUMMARY_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)


def stabilize_summary(page: Page, settle_ms: int = 3_000) -> None:
    """Wait a bit for account summary widgets and affordances to appear."""
    _stabilize_page(page, settle_ms=settle_ms)


def open_questions(page: Page) -> None:
    """Open the Mercado Libre seller questions page."""
    page.goto(QUESTIONS_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)


def stabilize_questions(page: Page, settle_ms: int = 3_000) -> None:
    """Wait a bit for seller questions lists, tabs and overlays to appear."""
    _stabilize_page(page, settle_ms=settle_ms)


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


def open_inbox(page: Page) -> None:
    """Open the primary inbox URL."""
    page.goto(INBOX_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)


def ensure_inbox_loaded(page: Page, timeout_ms: int = NAVIGATION_TIMEOUT_MS) -> bool:
    """Wait briefly for basic inbox signals or a clear blocked state."""
    deadline = time.monotonic() + max(timeout_ms, 0) / 1000
    while time.monotonic() < deadline:
        if _url_has_hint(page, INBOX_URL_HINTS):
            return True
        if _any_visible(page, INBOX_CONTAINER_SELECTORS):
            return True
        if _any_visible(page, INBOX_THREAD_SELECTORS):
            return True
        if _any_visible(page, INBOX_EMPTY_STATE_SELECTORS):
            return True
        if _any_visible(page, INBOX_DENIED_HINT_SELECTORS):
            return True
        page.wait_for_timeout(500)
    return _url_has_hint(page, INBOX_URL_HINTS) or _any_visible(page, INBOX_CONTAINER_SELECTORS)


def stabilize_inbox(page: Page, settle_ms: int = 5_000) -> None:
    """Wait for late client-side rendering with tolerant extra settling."""
    _stabilize_page(page, settle_ms=settle_ms)


def maybe_open_inbox_candidates(page: Page, timeout_ms: int = NAVIGATION_TIMEOUT_MS) -> str:
    """Try a short list of inbox URLs and keep the first usable result."""
    candidate_timeout_ms = max(timeout_ms // max(len(INBOX_CANDIDATE_URLS), 1), 1_000)

    try:
        open_inbox(page)
        if ensure_inbox_loaded(page, timeout_ms=candidate_timeout_ms):
            return page.url
    except Error:
        pass

    for url in INBOX_CANDIDATE_URLS:
        if url == INBOX_URL:
            continue
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT_MS)
        except Error:
            continue
        if ensure_inbox_loaded(page, timeout_ms=candidate_timeout_ms):
            return page.url
    return page.url
