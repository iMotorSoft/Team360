"""Minimal actions for the Mercado Libre browser lab."""

import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page

from .config import LOGIN_POLL_INTERVAL_SEC, WIZARD_KEYWORDS
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

MODAL_OVERLAY_SELECTORS: list[str] = [
    "[role='dialog']",
    "[aria-modal='true']",
    "[class*='modal']",
    "[class*='dialog']",
    "[class*='overlay']",
    "[class*='backdrop']",
    "[data-testid*='modal']",
    "[data-testid*='dialog']",
]

BANNER_LIKE_SELECTORS: list[str] = [
    "[role='banner']",
    "[class*='banner']",
    "[class*='onboarding']",
    "[class*='coachmark']",
    "[class*='tour']",
    "[class*='wizard']",
    "[data-testid*='banner']",
]

WIZARD_ACTION_KEYWORDS: tuple[str, ...] = (
    "entendido",
    "siguiente",
    "cerrar",
    "omitir",
    "finalizar",
    "guia",
    "guía",
    "tutorial",
    "bienvenido",
    "continuar",
    "start",
    "skip",
    "next",
    "close",
    "finish",
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


def _collect_keyword_hits(values: list[str], keywords: tuple[str, ...], limit: int = 8) -> list[str]:
    """Return a few keywords that appear in the provided text values."""
    normalized_values = [_normalize_for_match(value) for value in values if value]
    hits: list[str] = []
    for keyword in keywords:
        normalized_keyword = _normalize_for_match(keyword)
        if not normalized_keyword:
            continue
        if any(normalized_keyword in value for value in normalized_values) and keyword not in hits:
            hits.append(keyword)
        if len(hits) >= limit:
            break
    return hits


def _collect_special_layer_elements(page: Page, selectors: list[str], limit: int = 6) -> list[dict[str, object]]:
    """Collect a few visible overlay/banner candidates from the rendered DOM."""
    script = r"""
    ([selectors, limit]) => {
      const results = [];
      const seen = new Set();
      const isVisible = (node) => {
        const style = window.getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity || '1') === 0) {
          return false;
        }
        return rect.width > 0 && rect.height > 0;
      };

      for (const selector of selectors) {
        let nodes = [];
        try {
          nodes = Array.from(document.querySelectorAll(selector));
        } catch (_error) {
          nodes = [];
        }
        for (const node of nodes) {
          if (results.length >= limit) break;
          if (!isVisible(node)) continue;
          const rect = node.getBoundingClientRect();
          const style = window.getComputedStyle(node);
          const text = (node.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 200);
          const closeButtons = Array.from(node.querySelectorAll('button, [role="button"], a'))
            .map((child) => (child.innerText || child.getAttribute('aria-label') || child.getAttribute('title') || '').replace(/\s+/g, ' ').trim())
            .filter(Boolean)
            .slice(0, 4);
          const key = [selector, node.tagName, node.className, text].join('|');
          if (seen.has(key)) continue;
          seen.add(key);
          results.push({
            selector,
            tag: (node.tagName || '').toLowerCase(),
            role: node.getAttribute('role') || '',
            aria_modal: node.getAttribute('aria-modal') || '',
            class_name: (node.className || '').toString().trim().replace(/\s+/g, ' ').slice(0, 160),
            text,
            position: style.position || '',
            z_index: style.zIndex || '',
            viewport_ratio: Number(((rect.width * rect.height) / Math.max(window.innerWidth * window.innerHeight, 1)).toFixed(3)),
            close_affordances: closeButtons,
          });
        }
        if (results.length >= limit) break;
      }
      return results;
    }
    """
    result = _eval_with_arg_or(page, script, [selectors, limit], [])
    if not isinstance(result, list):
        return []

    items: list[dict[str, object]] = []
    for item in result:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "selector": str(item.get("selector", "")),
                "tag": str(item.get("tag", "")),
                "role": str(item.get("role", "")),
                "aria_modal": str(item.get("aria_modal", "")),
                "class_name": str(item.get("class_name", "")),
                "text": _clean_text(str(item.get("text", ""))),
                "position": str(item.get("position", "")),
                "z_index": str(item.get("z_index", "")),
                "viewport_ratio": float(item.get("viewport_ratio", 0) or 0),
                "close_affordances": [
                    _clean_text(str(value))
                    for value in item.get("close_affordances", [])
                    if str(value).strip()
                ],
            }
        )
    return items


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


def save_debug_screenshot(page: Page, path: Path, full_page: bool = False) -> None:
    """Save a basic screenshot for manual inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full_page)


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


def detect_wizard_or_onboarding(page: Page, keywords: tuple[str, ...] = WIZARD_KEYWORDS) -> dict[str, object]:
    """Detect visible onboarding-like copy and actions conservatively."""
    visible_buttons = find_visible_buttons(page, limit=20)
    visible_texts = first_visible_text_chunks(page, limit=30, max_len=160)
    button_texts = [
        " ".join(item.get(field, "") for field in ("text", "aria_label", "title"))
        for item in visible_buttons
    ]
    matched_keywords = _collect_keyword_hits(visible_texts + button_texts, keywords)
    matched_buttons = _filter_candidate_items(visible_buttons, WIZARD_ACTION_KEYWORDS)[:6]
    banner_like = detect_banner_like_elements(page)
    modal_overlay = detect_modal_overlay(page)
    detected = bool(matched_keywords and (matched_buttons or banner_like or modal_overlay.get("detected")))

    return {
        "detected": detected,
        "matched_keywords": matched_keywords,
        "matched_buttons": matched_buttons,
        "matching_text_samples": [
            text
            for text in visible_texts
            if any(_normalize_for_match(keyword) in _normalize_for_match(text) for keyword in matched_keywords)
        ][:6],
    }


def detect_modal_overlay(page: Page) -> dict[str, object]:
    """Detect a visible modal or blocking overlay with lightweight heuristics."""
    elements = _collect_special_layer_elements(page, MODAL_OVERLAY_SELECTORS)
    blocking = [
        item
        for item in elements
        if item.get("aria_modal")
        or item.get("position") == "fixed"
        or float(item.get("viewport_ratio", 0) or 0) >= 0.2
    ]
    return {
        "detected": bool(blocking),
        "count": len(elements),
        "blocking_count": len(blocking),
        "elements": elements,
    }


def detect_banner_like_elements(page: Page) -> list[dict[str, object]]:
    """Detect visible banner-like UI blocks that may affect what the page communicates."""
    return _collect_special_layer_elements(page, BANNER_LIKE_SELECTORS)


def collect_questions_inspection(page: Page, keywords: tuple[str, ...]) -> dict[str, object]:
    """Collect a compact inspection payload for seller questions discovery."""
    inspection = _collect_navigation_discovery(page, keywords)
    wizard_or_onboarding = detect_wizard_or_onboarding(page)
    modal_overlay = detect_modal_overlay(page)
    banner_like_elements = detect_banner_like_elements(page)
    warnings = list(inspection.get("warnings", []))

    if wizard_or_onboarding.get("detected"):
        warnings.append("wizard or onboarding hints detected; validate screenshot before trusting visible affordances")
    if modal_overlay.get("detected"):
        warnings.append("modal or overlay detected; page content may be partially blocked")
    if banner_like_elements:
        warnings.append("banner-like UI detected; some visible copy may be promotional or onboarding-related")
    if not inspection.get("candidate_links") and not inspection.get("candidate_buttons"):
        warnings.append("questions-related affordances were not clearly visible on this pass")

    inspection["wizard_or_onboarding"] = wizard_or_onboarding
    inspection["modal_overlay"] = modal_overlay
    inspection["banner_like_elements"] = banner_like_elements
    inspection["warnings"] = warnings
    return inspection


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
