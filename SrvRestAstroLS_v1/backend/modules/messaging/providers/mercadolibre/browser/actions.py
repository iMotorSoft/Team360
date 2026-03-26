"""Minimal actions for the Mercado Libre browser lab."""

import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page

from .config import LOGIN_POLL_INTERVAL_SEC
from .selectors import (
    ACCOUNT_MENU_SELECTORS,
    ACCOUNT_URL_HINTS,
    INBOX_CONTAINER_SELECTORS,
    INBOX_DENIED_HINT_SELECTORS,
    INBOX_EMPTY_STATE_SELECTORS,
    INBOX_SELECTOR_GROUPS,
    INBOX_THREAD_SELECTORS,
    INBOX_URL_HINTS,
    LOGIN_ENTRY_SELECTORS,
    LOGIN_URL_HINTS,
    SESSION_COOKIE_NAMES,
)

ROOT_CANDIDATE_SELECTORS: list[str] = [
    "#root",
    "#__next",
    "main",
    "section",
    "article",
    "div[role]",
    "[role='main']",
    "iframe",
]


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


def _clean_text(value: str) -> str:
    """Normalize whitespace for compact debug output."""
    return " ".join(value.split())[:200]


def _normalize_for_match(value: str) -> str:
    """Normalize text for conservative keyword matching."""
    cleaned = unicodedata.normalize("NFKD", value or "")
    cleaned = "".join(char for char in cleaned if not unicodedata.combining(char))
    return " ".join(cleaned.lower().split())


def _eval_or(page: Page, script: str, default):
    """Evaluate a browser script and keep a default on failure."""
    try:
        return page.evaluate(script)
    except Error:
        return default


def _eval_with_arg_or(page: Page, script: str, arg, default):
    """Evaluate a browser script with one argument and keep a default on failure."""
    try:
        return page.evaluate(script, arg)
    except Error:
        return default


def _collect_visible_elements(page: Page, selector: str, limit: int) -> list[dict[str, str]]:
    """Collect a few visible elements and their useful attributes."""
    items: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str]] = set()
    try:
        locator = page.locator(selector)
        total = min(locator.count(), max(limit * 4, limit))
    except Error:
        return items

    for index in range(total):
        if len(items) >= limit:
            break
        try:
            item = locator.nth(index)
            if not item.is_visible():
                continue
        except Error:
            continue
        try:
            text = _clean_text(item.inner_text(timeout=1_000))
        except Error:
            try:
                text = _clean_text(item.text_content() or "")
            except Error:
                text = ""
        try:
            href = item.get_attribute("href") or ""
        except Error:
            href = ""
        try:
            aria_label = item.get_attribute("aria-label") or ""
        except Error:
            aria_label = ""
        try:
            title = item.get_attribute("title") or ""
        except Error:
            title = ""
        payload = {
            "text": text,
            "href": href,
            "aria_label": aria_label,
            "title": title,
        }
        key = (payload["text"], payload["href"], payload["aria_label"], payload["title"])
        if not any(key) or key in seen:
            continue
        seen.add(key)
        items.append(payload)
    return items


def _filter_candidate_items(items: list[dict[str, str]], keywords: tuple[str, ...]) -> list[dict[str, str]]:
    """Keep only visible items that match any discovery keyword."""
    normalized_keywords = tuple(_normalize_for_match(keyword) for keyword in keywords)
    matches: list[dict[str, str]] = []
    for item in items:
        haystack = " ".join(
            _normalize_for_match(item.get(field, ""))
            for field in ("text", "href", "aria_label", "title")
        )
        if any(keyword and keyword in haystack for keyword in normalized_keywords):
            matches.append(item)
    return matches


def _collect_navigation_discovery(page: Page, keywords: tuple[str, ...]) -> dict[str, object]:
    """Collect visible affordances and filtered candidates on one page."""
    metrics = collect_page_document_metrics(page)
    visible_links = find_visible_links(page)
    visible_buttons = find_visible_buttons(page)
    candidate_links = filter_candidate_links(visible_links, keywords)
    candidate_buttons = filter_candidate_buttons(visible_buttons, keywords)
    global_text_samples = first_visible_text_chunks(page)
    warnings: list[str] = []

    if not global_text_samples:
        warnings.append("no visible global text chunks found")
    if not visible_links:
        warnings.append("no visible links found")
    if not visible_buttons:
        warnings.append("no visible buttons found")
    if not candidate_links and not candidate_buttons:
        warnings.append("no candidate affordances matched discovery keywords")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "final_url": get_current_url(page),
        "page_title": get_page_title(page),
        "logged_in_heuristic": is_logged_in(page),
        "document_metrics": metrics,
        "global_text_samples": global_text_samples,
        "visible_links": visible_links,
        "candidate_links": candidate_links,
        "visible_buttons": visible_buttons,
        "candidate_buttons": candidate_buttons,
        "warnings": warnings,
    }


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


def save_text_report(path: Path, text: str) -> None:
    """Persist a plain-text debug report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def get_current_url(page: Page) -> str:
    """Return the current page URL."""
    return page.url


def get_page_title(page: Page) -> str:
    """Return the page title, or an empty string on failure."""
    try:
        return _clean_text(page.title())
    except Error:
        return ""


def get_document_ready_state(page: Page) -> str:
    """Return document.readyState or an empty string on failure."""
    return str(_eval_or(page, "document.readyState", "") or "")


def get_body_text_length(page: Page) -> int:
    """Return the body innerText length."""
    return int(_eval_or(page, "(document.body && document.body.innerText || '').length", 0) or 0)


def get_body_html_length(page: Page) -> int:
    """Return the body innerHTML length."""
    return int(_eval_or(page, "(document.body && document.body.innerHTML || '').length", 0) or 0)


def get_iframe_count(page: Page) -> int:
    """Return the number of iframes in the document."""
    return int(_eval_or(page, "document.querySelectorAll('iframe').length", 0) or 0)


def get_anchor_count(page: Page) -> int:
    """Return the number of anchors in the document."""
    return int(_eval_or(page, "document.querySelectorAll('a').length", 0) or 0)


def get_button_count(page: Page) -> int:
    """Return the number of buttons in the document."""
    return int(_eval_or(page, "document.querySelectorAll('button').length", 0) or 0)


def collect_page_document_metrics(page: Page) -> dict[str, object]:
    """Collect basic document metrics for the current page."""
    return {
        "ready_state": get_document_ready_state(page),
        "iframe_count": get_iframe_count(page),
        "anchor_count": get_anchor_count(page),
        "button_count": get_button_count(page),
        "body_text_length": get_body_text_length(page),
        "body_html_length": get_body_html_length(page),
    }


def count_matches(page: Page, selectors: list[str]) -> dict[str, int]:
    """Count DOM matches for each selector."""
    counts: dict[str, int] = {}
    for selector in selectors:
        try:
            counts[selector] = page.locator(selector).count()
        except Error:
            counts[selector] = 0
    return counts


def find_visible_links(page: Page, limit: int = 50) -> list[dict[str, str]]:
    """Collect a sample of visible links from the current page."""
    return _collect_visible_elements(page, "a", limit=limit)


def find_visible_buttons(page: Page, limit: int = 30) -> list[dict[str, str]]:
    """Collect a sample of visible buttons from the current page."""
    items = _collect_visible_elements(page, "button", limit=limit)
    if len(items) >= limit:
        return items
    extra = _collect_visible_elements(page, "[role='button']", limit=limit)
    seen = {(item["text"], item["href"], item["aria_label"], item["title"]) for item in items}
    for item in extra:
        key = (item["text"], item["href"], item["aria_label"], item["title"])
        if key in seen:
            continue
        items.append(item)
        seen.add(key)
        if len(items) >= limit:
            break
    return items


def filter_candidate_links(items: list[dict[str, str]], keywords: tuple[str, ...]) -> list[dict[str, str]]:
    """Keep only links that look related to messages, sales or account areas."""
    return _filter_candidate_items(items, keywords)


def filter_candidate_buttons(items: list[dict[str, str]], keywords: tuple[str, ...]) -> list[dict[str, str]]:
    """Keep only buttons that look related to messages, sales or account areas."""
    return _filter_candidate_items(items, keywords)


def sample_texts_for_selector(page: Page, selector: str, limit: int = 5) -> list[str]:
    """Collect a few short visible texts for one selector."""
    samples: list[str] = []
    try:
        locator = page.locator(selector)
        total = min(locator.count(), max(limit * 3, limit))
    except Error:
        return samples

    for index in range(total):
        if len(samples) >= limit:
            break
        try:
            item = locator.nth(index)
            if not item.is_visible():
                continue
        except Error:
            continue
        try:
            text = item.inner_text(timeout=1_000)
        except Error:
            try:
                text = item.text_content() or ""
            except Error:
                continue
        cleaned = _clean_text(text)
        if cleaned and cleaned not in samples:
            samples.append(cleaned)
    return samples


def first_visible_text_chunks(page: Page, limit: int = 20, max_len: int = 120) -> list[str]:
    """Collect some short visible text chunks from the rendered body."""
    script = r"""
    ([limit, maxLen]) => {
      const nodes = Array.from(document.querySelectorAll('body *'));
      const samples = [];
      for (const node of nodes) {
        if (samples.length >= limit) break;
        const style = window.getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (rect.width === 0 || rect.height === 0) continue;
        const text = (node.innerText || '').replace(/\s+/g, ' ').trim();
        if (!text) continue;
        const chunk = text.slice(0, maxLen);
        if (!samples.includes(chunk)) samples.push(chunk);
      }
      return samples;
    }
    """
    result = _eval_with_arg_or(page, script, [limit, max_len], [])
    if not isinstance(result, list):
        return []
    return [_clean_text(str(item))[:max_len] for item in result if str(item).strip()]


def get_root_structure_signals(page: Page, limit: int = 12) -> list[dict[str, object]]:
    """Collect a few top-level body nodes and their main attributes."""
    script = r"""
    (limit) => {
      const children = Array.from(document.body ? document.body.children : []).slice(0, limit);
      return children.map((node) => ({
        tag: (node.tagName || '').toLowerCase(),
        id: node.id || '',
        class_name: (node.className || '').toString().trim().replace(/\s+/g, ' ').slice(0, 120),
        role: node.getAttribute('role') || '',
        child_count: node.children ? node.children.length : 0,
        text_length: ((node.innerText || '').trim()).length,
      }));
    }
    """
    result = _eval_with_arg_or(page, script, limit, [])
    if not isinstance(result, list):
        return []
    clean_nodes: list[dict[str, object]] = []
    for node in result:
        if not isinstance(node, dict):
            continue
        clean_nodes.append(
            {
                "tag": str(node.get("tag", "")),
                "id": str(node.get("id", "")),
                "class_name": str(node.get("class_name", "")),
                "role": str(node.get("role", "")),
                "child_count": int(node.get("child_count", 0) or 0),
                "text_length": int(node.get("text_length", 0) or 0),
            }
        )
    return clean_nodes


def _count_visible(page: Page, selector: str, limit: int = 50) -> int:
    """Count visible matches for one selector with a defensive limit."""
    try:
        locator = page.locator(selector)
        total = min(locator.count(), limit)
    except Error:
        return 0

    visible = 0
    for index in range(total):
        try:
            if locator.nth(index).is_visible():
                visible += 1
        except Error:
            continue
    return visible


def count_visible_threads(page: Page) -> int:
    """Return an approximate visible thread count."""
    return max((_count_visible(page, selector) for selector in INBOX_THREAD_SELECTORS), default=0)


def inbox_has_threads(page: Page) -> bool:
    """Return True when at least one visible thread is detected."""
    return count_visible_threads(page) > 0


def inbox_empty_state(page: Page) -> bool:
    """Return True when an empty inbox hint is visible."""
    return _any_visible(page, INBOX_EMPTY_STATE_SELECTORS)


def can_access_inbox(page: Page) -> bool:
    """Return True when the inbox appears reachable with the current session."""
    if inbox_has_threads(page) or inbox_empty_state(page):
        return True
    if _any_visible(page, INBOX_DENIED_HINT_SELECTORS) and not is_logged_in(page):
        return False
    if _any_visible(page, INBOX_CONTAINER_SELECTORS) and _url_has_hint(page, INBOX_URL_HINTS):
        return True
    return _url_has_hint(page, INBOX_URL_HINTS) and is_logged_in(page)


def collect_home_inspection(page: Page, keywords: tuple[str, ...]) -> dict[str, object]:
    """Collect a compact inspection payload for authenticated home discovery."""
    return _collect_navigation_discovery(page, keywords)


def collect_summary_inspection(page: Page, keywords: tuple[str, ...]) -> dict[str, object]:
    """Collect a compact inspection payload for account summary discovery."""
    return _collect_navigation_discovery(page, keywords)


def collect_inbox_inspection(page: Page) -> dict[str, object]:
    """Collect a compact inspection payload for inbox selector tuning."""
    groups: dict[str, dict[str, object]] = {}
    warnings: list[str] = []
    root_selector_counts = count_matches(page, ROOT_CANDIDATE_SELECTORS)
    global_text_samples = first_visible_text_chunks(page)

    for group_name, selectors in INBOX_SELECTOR_GROUPS.items():
        counts = count_matches(page, selectors)
        samples = {
            selector: sample_texts_for_selector(page, selector)
            for selector, count in counts.items()
            if count > 0
        }
        samples = {selector: texts for selector, texts in samples.items() if texts}
        if not any(count > 0 for count in counts.values()):
            warnings.append(f"no selector matched in group {group_name}")
        groups[group_name] = {
            "counts": counts,
            "samples": samples,
        }

    if not any(count > 0 for count in root_selector_counts.values()):
        warnings.append("no generic root selector matched")
    if not global_text_samples:
        warnings.append("no visible global text chunks found")

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "final_url": get_current_url(page),
        "page_title": get_page_title(page),
        "ready_state": get_document_ready_state(page),
        "logged_in_heuristic": is_logged_in(page),
        "inbox_accessible_heuristic": can_access_inbox(page),
        "visible_threads_heuristic": count_visible_threads(page),
        "empty_state_heuristic": inbox_empty_state(page),
        "iframe_count": get_iframe_count(page),
        "anchor_count": get_anchor_count(page),
        "button_count": get_button_count(page),
        "body_text_length": get_body_text_length(page),
        "body_html_length": get_body_html_length(page),
        "root_selector_counts": root_selector_counts,
        "root_nodes": get_root_structure_signals(page),
        "global_text_samples": global_text_samples,
        "groups": groups,
        "warnings": warnings,
    }
