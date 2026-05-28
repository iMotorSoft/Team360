from __future__ import annotations

import re
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from config import get_settings, storage_state_path


HITL_PATTERNS = [
    r"2fa",
    r"two-factor",
    r"verificaci[oó]n",
    r"c[oó]digo",
    r"captcha",
    r"aprobar inicio",
    r"security check",
]


def _state_file(name: str) -> Path:
    return storage_state_path(name)


@contextmanager
def browser_context(name: str) -> Iterator[tuple[object, object, object, object]]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright no esta instalado. Ejecutar: pip install -r requirements.txt "
            "y luego playwright install chromium"
        ) from exc

    settings = get_settings()
    state_file = _state_file(name)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=settings.headless,
            slow_mo=150 if not settings.headless else 0,
        )
        context_kwargs = {
            "viewport": {"width": 1440, "height": 1000},
            "locale": "es-AR",
            "timezone_id": "America/Argentina/Buenos_Aires",
        }
        if state_file.exists():
            context_kwargs["storage_state"] = str(state_file)
            print(f"[session] reutilizando storage_state: {state_file}")
        context = browser.new_context(**context_kwargs)
        context.set_default_timeout(settings.timeout_ms)
        page = context.new_page()
        page.set_default_timeout(settings.timeout_ms)
        try:
            yield playwright, browser, context, page
        finally:
            context.close()
            browser.close()


def save_storage_state(context, name: str) -> Path:
    state_file = _state_file(name)
    context.storage_state(path=str(state_file))
    print(f"[session] storage_state guardado: {state_file}")
    return state_file


def visible_text(page, limit: int = 20000) -> str:
    try:
        text = page.locator("body").inner_text(timeout=10000)
    except Exception as exc:
        return f"[visible_text_error] {exc}"
    return text[:limit]


def detect_manual_challenge(page) -> bool:
    text = visible_text(page, limit=8000).lower()
    url = page.url.lower()
    haystack = f"{url}\n{text}"
    return any(re.search(pattern, haystack, re.I) for pattern in HITL_PATTERNS)


def wait_for_human_if_needed(page, label: str) -> bool:
    if not detect_manual_challenge(page):
        return False
    print(f"[hitl] {label}: parece haber 2FA/captcha/verificacion manual.")
    print("[hitl] Completar en el navegador abierto y presionar ENTER aqui para continuar.")
    input()
    return True


def fill_first(page, selectors: list[str], value: str, label: str) -> bool:
    if not value:
        return False
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible(timeout=2000):
                locator.fill(value)
                print(f"[form] {label}: selector {selector}")
                return True
        except Exception:
            continue
    print(f"[form] {label}: no se encontro selector confiable")
    return False


def click_first(page, selectors: list[str], label: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible(timeout=2000):
                locator.click()
                print(f"[form] {label}: selector {selector}")
                return True
        except Exception:
            continue
    print(f"[form] {label}: no se encontro selector confiable")
    return False


def write_visible_text(page, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(visible_text(page), encoding="utf-8")
    print(f"[inspect] texto visible guardado: {path}")
    return path
