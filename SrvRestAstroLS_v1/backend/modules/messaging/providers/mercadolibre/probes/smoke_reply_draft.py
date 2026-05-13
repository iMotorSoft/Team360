"""Smoke probe for draft-only reply validation on Mercado Libre seller questions."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Locator, Page, sync_playwright

from ..browser.actions import (
    collect_questions_list_inspection,
    extract_question_item_summary,
    maybe_save_storage_state,
    save_debug_screenshot,
    save_text_report,
)
from ..browser.config import DEFAULT_PROFILE_NAME, INSPECT_DIR
from ..browser.context import close_context, open_persistent_context
from ..browser.pages import open_questions, stabilize_questions
from ..browser.session_store import get_screenshot_path, get_storage_state_path

DEFAULT_DRAFT_TEXT = (
    "Hola, gracias por escribirnos. Estamos revisando tu consulta para responderte con precision."
)
QUESTION_ITEM_SELECTOR = ".sc-item"
REPLY_BUTTON_TEXT = "Responder"
TEXTAREA_SELECTOR = "textarea[name='response_text']"
QUICK_REPLY_BUTTON_TEXT = "Respuestas rapidas"
COOKIE_ACCEPT_BUTTON_TEXT = "Aceptar cookies"


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Draft-only reply smoke for Mercado Libre persistent browser sessions.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME, help="Persistent browser profile name.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds reserved for page loading and UI stabilization.")
    parser.add_argument(
        "--draft-text",
        default=DEFAULT_DRAFT_TEXT,
        help="Text to inject into the reply textarea for draft validation.",
    )
    parser.add_argument(
        "--keep-draft",
        action="store_true",
        help="Keep the draft text in the textarea instead of clearing it before closing.",
    )
    return parser.parse_args()


def log(message: str) -> None:
    """Print a short progress message."""
    print(message, flush=True)


def _safe_name(value: str) -> str:
    """Keep generated runtime names filesystem-friendly."""
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value).strip("_") or "default"


def _get_report_path(profile_name: str) -> Path:
    """Return a timestamped text report path for reply-draft validation."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return INSPECT_DIR / f"reply_draft_{_safe_name(profile_name)}_{stamp}.txt"


def _click_cookie_accept_if_present(page: Page) -> bool:
    """Dismiss the cookie banner when present and visible."""
    try:
        button = page.locator(f"button:has-text('{COOKIE_ACCEPT_BUTTON_TEXT}')")
        if button.count() > 0 and button.first.is_visible():
            button.first.click()
            page.wait_for_timeout(500)
            return True
    except Error:
        return False
    return False


def _find_first_reply_target(page: Page) -> tuple[Locator | None, Locator | None, dict[str, str]]:
    """Return the first visible question item that exposes a usable reply affordance."""
    try:
        items = page.locator(QUESTION_ITEM_SELECTOR)
        total = items.count()
    except Error:
        return None, None, {}

    fallback_item: Locator | None = None
    fallback_button: Locator | None = None
    fallback_summary: dict[str, str] = {}

    for index in range(total):
        try:
            item = items.nth(index)
            if not item.is_visible():
                continue
        except Error:
            continue

        button = item.locator(f"button:has-text('{REPLY_BUTTON_TEXT}')")
        try:
            if button.count() <= 0 or not button.first.is_visible():
                continue
        except Error:
            continue

        summary = extract_question_item_summary(item)
        textarea = item.locator(TEXTAREA_SELECTOR)
        try:
            if textarea.count() > 0 and textarea.first.is_visible():
                return item, button.first, summary
        except Error:
            pass

        try:
            if not button.first.is_disabled():
                return item, button.first, summary
        except Error:
            pass

        if fallback_item is None:
            fallback_item = item
            fallback_button = button.first
            fallback_summary = summary

    return fallback_item, fallback_button, fallback_summary


def _reply_form_state(item: Locator) -> dict[str, object]:
    """Read the visible state of the inline reply form within one question item."""
    textarea = item.locator(TEXTAREA_SELECTOR).first
    responder_button = item.locator(f"button:has-text('{REPLY_BUTTON_TEXT}')").last
    quick_reply_button = item.locator(f"button:has-text('{QUICK_REPLY_BUTTON_TEXT}')").first
    textarea_present = textarea.count() > 0
    responder_present = responder_button.count() > 0

    counter_text = ""
    try:
        counter_candidates = item.locator("text=/caracteres restantes/i")
        if counter_candidates.count() > 0 and counter_candidates.first.is_visible():
            counter_text = counter_candidates.first.inner_text(timeout=500).strip()
    except Error:
        counter_text = ""

    quick_reply_visible = False
    try:
        quick_reply_visible = quick_reply_button.count() > 0 and quick_reply_button.is_visible()
    except Error:
        quick_reply_visible = False

    return {
        "textarea_visible": textarea_present and textarea.is_visible(),
        "textarea_placeholder": (textarea.get_attribute("placeholder") or "") if textarea_present else "",
        "textarea_name": (textarea.get_attribute("name") or "") if textarea_present else "",
        "textarea_maxlength": (textarea.get_attribute("maxlength") or "") if textarea_present else "",
        "textarea_value_length": len(textarea.input_value() or "") if textarea_present else 0,
        "responder_disabled": responder_button.is_disabled() if responder_present else True,
        "responder_text": responder_button.inner_text(timeout=500).strip() if responder_present else "",
        "quick_reply_visible": quick_reply_visible,
        "counter_text": counter_text,
    }


def _format_report(profile_name: str, result: dict[str, object]) -> str:
    """Render a compact text report for reply-draft validation."""
    question = result.get("question_summary", {})
    before = result.get("before_fill", {})
    after = result.get("after_fill", {})
    after_clear = result.get("after_clear", {})
    inspection = result.get("questions_list_inspection", {})
    warnings = result.get("warnings", [])

    lines = [
        f"profile: {profile_name}",
        f"timestamp: {result.get('timestamp', '')}",
        f"final url: {result.get('final_url', '')}",
        f"page title: {result.get('page_title', '')}",
        f"logged_in heuristic: {result.get('logged_in_heuristic', False)}",
        f"questions_page_reached heuristic: {result.get('questions_page_reached', False)}",
        f"reply_target_found: {result.get('reply_target_found', False)}",
        f"draft_validated: {result.get('draft_validated', False)}",
        f"draft_cleared: {result.get('draft_cleared', False)}",
        f"cookies_accepted: {result.get('cookies_accepted', False)}",
        f"draft_length: {result.get('draft_length', 0)}",
        "",
        "[question_summary]",
        f"text_snippet: {question.get('text_snippet', '')}",
        f"product_hint: {question.get('product_hint', '')}",
        f"product_href: {question.get('product_href', '')}",
        f"buyer_hint: {question.get('buyer_hint', '')}",
        f"time_hint: {question.get('time_hint', '')}",
        f"status_hint: {question.get('status_hint', '')}",
        f"cta_hint: {question.get('cta_hint', '')}",
        "",
        "[before_fill]",
        f"textarea_visible: {before.get('textarea_visible', False)}",
        f"textarea_placeholder: {before.get('textarea_placeholder', '')}",
        f"textarea_name: {before.get('textarea_name', '')}",
        f"textarea_maxlength: {before.get('textarea_maxlength', '')}",
        f"textarea_value_length: {before.get('textarea_value_length', 0)}",
        f"responder_disabled: {before.get('responder_disabled', False)}",
        f"quick_reply_visible: {before.get('quick_reply_visible', False)}",
        f"counter_text: {before.get('counter_text', '')}",
        "",
        "[after_fill]",
        f"textarea_value_length: {after.get('textarea_value_length', 0)}",
        f"responder_disabled: {after.get('responder_disabled', False)}",
        f"quick_reply_visible: {after.get('quick_reply_visible', False)}",
        f"counter_text: {after.get('counter_text', '')}",
        "",
        "[after_clear]",
        f"textarea_value_length: {after_clear.get('textarea_value_length', 0)}",
        f"responder_disabled: {after_clear.get('responder_disabled', False)}",
        f"counter_text: {after_clear.get('counter_text', '')}",
        "",
        "[questions_list_probe]",
        f"item_selector: {inspection.get('item_selector', '')}",
        f"item_count_heuristic: {inspection.get('item_count_heuristic', 0)}",
        f"filters_detected: {len(inspection.get('visible_filters', []))}",
    ]

    if warnings:
        lines.append("")
        lines.append("warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def _save_artifacts(
    page: Page | None,
    context: BrowserContext | None,
    screenshot_path: Path,
    storage_state_path: Path,
) -> None:
    """Persist a screenshot and storage state when possible."""
    if page is not None and not page.is_closed():
        save_debug_screenshot(page, screenshot_path, full_page=True)
        log(f"screenshot guardado en {screenshot_path}")
    if context is not None:
        maybe_save_storage_state(context, storage_state_path)
        log(f"storage state guardado en {storage_state_path}")


def run(profile_name: str, timeout_sec: int, draft_text: str, keep_draft: bool) -> int:
    """Execute the draft-only reply validation flow."""
    screenshot_path = get_screenshot_path(prefix=f"smoke_reply_draft_{profile_name}")
    storage_state_path = get_storage_state_path(profile_name)
    report_path = _get_report_path(profile_name)

    context: BrowserContext | None = None
    page: Page | None = None
    result: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reply_target_found": False,
        "draft_validated": False,
        "draft_cleared": False,
        "cookies_accepted": False,
        "draft_length": len(draft_text),
        "question_summary": {},
        "before_fill": {},
        "after_fill": {},
        "after_clear": {},
        "questions_list_inspection": {},
        "warnings": [],
    }
    ok = False

    log("iniciando browser persistente")
    log(f"profile usado: {profile_name}")

    with sync_playwright() as playwright:
        try:
            context, page = open_persistent_context(playwright, profile_name=profile_name)
            log("abriendo preguntas del vendedor en Mercado Libre")
            open_questions(page)
            settle_ms = max(3_000, min(max(timeout_sec, 1), 10) * 500)
            stabilize_questions(page, settle_ms=settle_ms)

            result["cookies_accepted"] = _click_cookie_accept_if_present(page)
            result["questions_list_inspection"] = collect_questions_list_inspection(page)
            result["final_url"] = page.url
            result["page_title"] = page.title()
            result["logged_in_heuristic"] = bool(result["questions_list_inspection"].get("logged_in_heuristic"))
            result["questions_page_reached"] = "/preguntas/" in page.url.lower()

            item, reply_button, question_summary = _find_first_reply_target(page)
            result["question_summary"] = question_summary
            if item is None or reply_button is None:
                result["warnings"].append("no visible reply target found on current questions page")
            else:
                result["reply_target_found"] = True
                before_fill = _reply_form_state(item)
                result["before_fill"] = before_fill
                if not before_fill.get("textarea_visible"):
                    if before_fill.get("responder_disabled"):
                        result["warnings"].append("reply button was disabled before a textarea became visible")
                    else:
                        reply_button.click()
                        page.wait_for_timeout(1_000)
                        before_fill = _reply_form_state(item)
                        result["before_fill"] = before_fill

                if not before_fill.get("textarea_visible"):
                    result["warnings"].append("reply textarea did not appear after opening the item")
                else:
                    textarea = item.locator(TEXTAREA_SELECTOR).first
                    textarea.fill(draft_text)
                    page.wait_for_timeout(700)
                    after_fill = _reply_form_state(item)
                    result["after_fill"] = after_fill

                    if not after_fill.get("responder_disabled", True) and int(after_fill.get("textarea_value_length", 0) or 0) > 0:
                        result["draft_validated"] = True

                    if not keep_draft:
                        textarea.fill("")
                        page.wait_for_timeout(500)
                        result["after_clear"] = _reply_form_state(item)
                        result["draft_cleared"] = int(result["after_clear"].get("textarea_value_length", 0) or 0) == 0

            save_text_report(report_path, _format_report(profile_name, result))
            log(f"final url {result.get('final_url', '')}")
            log(f"page title {result.get('page_title', '')}")
            log(f"reply_target_found {result.get('reply_target_found', False)}")
            log(f"draft_validated {result.get('draft_validated', False)}")
            log(f"draft_cleared {result.get('draft_cleared', False)}")
            log(f"question text {question_summary.get('text_snippet', '')}")
            log(f"question product {question_summary.get('product_hint', '')}")
            log(f"report guardado en {report_path}")
            ok = bool(
                result.get("logged_in_heuristic")
                and result.get("questions_page_reached")
                and result.get("reply_target_found")
                and result.get("draft_validated")
            )
        except Exception as exc:
            log(f"error durante smoke reply draft: {exc}")
            result["warnings"].append(str(exc))
        finally:
            try:
                save_text_report(report_path, _format_report(profile_name, result))
            except Exception:
                pass
            try:
                _save_artifacts(page, context, screenshot_path, storage_state_path)
            except Exception as exc:
                log(f"no se pudieron guardar artifacts: {exc}")
            close_context(context)

    log(f"profile {profile_name}")
    log(f"final_url {result.get('final_url', '')}")
    log(f"page_title {result.get('page_title', '')}")
    log(f"reply_target_found {result.get('reply_target_found', False)}")
    log(f"draft_validated {result.get('draft_validated', False)}")
    log(f"draft_cleared {result.get('draft_cleared', False)}")
    log(f"screenshot path {screenshot_path}")
    log(f"report path {report_path}")
    log("fin")
    return 0 if ok else 1


def main() -> int:
    """Run the probe from the command line."""
    args = parse_args()
    return run(
        profile_name=args.profile,
        timeout_sec=args.timeout,
        draft_text=args.draft_text,
        keep_draft=args.keep_draft,
    )


if __name__ == "__main__":
    raise SystemExit(main())
