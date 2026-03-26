"""Inspection probe for Mercado Libre authenticated home discovery."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from ..browser.actions import (
    collect_home_inspection,
    maybe_save_storage_state,
    save_debug_screenshot,
    save_text_report,
)
from ..browser.config import DEFAULT_PROFILE_NAME, HOME_DISCOVERY_KEYWORDS, INSPECT_DIR
from ..browser.context import close_context, open_persistent_context
from ..browser.pages import open_home, stabilize_home
from ..browser.session_store import get_screenshot_path, get_storage_state_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Home inspection smoke for Mercado Libre persistent browser sessions.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME, help="Persistent browser profile name.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds reserved for future home loading adjustments.")
    return parser.parse_args()


def log(message: str) -> None:
    """Print a short progress message."""
    print(message, flush=True)


def _safe_name(value: str) -> str:
    """Keep generated runtime names filesystem-friendly."""
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value).strip("_") or "default"


def _get_report_path(profile_name: str) -> Path:
    """Return a timestamped text report path for home inspection."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return INSPECT_DIR / f"home_inspect_{_safe_name(profile_name)}_{stamp}.txt"


def _format_item(item: dict[str, str]) -> str:
    """Render a link or button item in one compact line."""
    return (
        f"text={item.get('text', '')} | href={item.get('href', '')} | "
        f"aria_label={item.get('aria_label', '')} | title={item.get('title', '')}"
    )


def _format_report(profile_name: str, inspection: dict[str, object]) -> str:
    """Render a compact text report for manual navigation discovery."""
    metrics = inspection.get("document_metrics", {})
    global_text_samples = inspection.get("global_text_samples", [])
    visible_links = inspection.get("visible_links", [])
    candidate_links = inspection.get("candidate_links", [])
    visible_buttons = inspection.get("visible_buttons", [])
    candidate_buttons = inspection.get("candidate_buttons", [])
    warnings = inspection.get("warnings", [])

    lines = [
        f"profile: {profile_name}",
        f"timestamp: {inspection.get('timestamp', '')}",
        f"final url: {inspection.get('final_url', '')}",
        f"page title: {inspection.get('page_title', '')}",
        f"logged_in heuristic: {inspection.get('logged_in_heuristic', False)}",
        "",
        "[document_metrics]",
        f"ready_state: {metrics.get('ready_state', '')}",
        f"iframe_count: {metrics.get('iframe_count', 0)}",
        f"anchor_count: {metrics.get('anchor_count', 0)}",
        f"button_count: {metrics.get('button_count', 0)}",
        f"body_text_length: {metrics.get('body_text_length', 0)}",
        f"body_html_length: {metrics.get('body_html_length', 0)}",
        "",
        "[global_text_samples]",
    ]

    for text in global_text_samples:
        lines.append(f"- {text}")

    lines.append("")
    lines.append("[visible_links]")
    for item in visible_links:
        lines.append(f"- {_format_item(item)}")

    lines.append("")
    lines.append("[candidate_links]")
    for item in candidate_links:
        lines.append(f"- {_format_item(item)}")

    lines.append("")
    lines.append("[visible_buttons]")
    for item in visible_buttons:
        lines.append(f"- {_format_item(item)}")

    lines.append("")
    lines.append("[candidate_buttons]")
    for item in candidate_buttons:
        lines.append(f"- {_format_item(item)}")

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
        save_debug_screenshot(page, screenshot_path)
        log(f"screenshot guardado en {screenshot_path}")
    if context is not None:
        maybe_save_storage_state(context, storage_state_path)
        log(f"storage state guardado en {storage_state_path}")


def run(profile_name: str, timeout_sec: int) -> int:
    """Execute the authenticated home inspection flow."""
    screenshot_path = get_screenshot_path(prefix=f"smoke_home_inspect_{profile_name}")
    storage_state_path = get_storage_state_path(profile_name)
    report_path = _get_report_path(profile_name)

    context: BrowserContext | None = None
    page: Page | None = None
    inspection: dict[str, object] = {}
    ok = False

    log("iniciando browser persistente")
    log(f"profile usado: {profile_name}")

    with sync_playwright() as playwright:
        try:
            context, page = open_persistent_context(playwright, profile_name=profile_name)
            log("abriendo home Mercado Libre")
            open_home(page)
            settle_ms = max(3_000, min(max(timeout_sec, 1), 10) * 500)
            stabilize_home(page, settle_ms=settle_ms)

            inspection = collect_home_inspection(page, keywords=HOME_DISCOVERY_KEYWORDS)
            save_text_report(report_path, _format_report(profile_name, inspection))
            log(f"final url {inspection.get('final_url', '')}")
            log(f"page title {inspection.get('page_title', '')}")
            log(f"sesion activa {inspection.get('logged_in_heuristic', False)}")
            log(f"links visibles {len(inspection.get('visible_links', []))}")
            log(f"botones visibles {len(inspection.get('visible_buttons', []))}")
            log(f"links candidatos {len(inspection.get('candidate_links', []))}")
            log(f"botones candidatos {len(inspection.get('candidate_buttons', []))}")
            if inspection.get("warnings"):
                log(f"warnings {inspection.get('warnings')}")
            log(f"report guardado en {report_path}")
            ok = bool(inspection.get("logged_in_heuristic"))
        except Exception as exc:
            log(f"error durante smoke home inspect: {exc}")
        finally:
            try:
                _save_artifacts(page, context, screenshot_path, storage_state_path)
            except Exception as exc:
                log(f"no se pudieron guardar artifacts: {exc}")
            close_context(context)

    log(f"final_url {inspection.get('final_url', '')}")
    log(f"page_title {inspection.get('page_title', '')}")
    log(f"logged_in {inspection.get('logged_in_heuristic', False)}")
    log(f"screenshot path {screenshot_path}")
    log(f"report path {report_path}")
    log("fin")
    return 0 if ok else 1


def main() -> int:
    """Run the probe from the command line."""
    args = parse_args()
    return run(profile_name=args.profile, timeout_sec=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())
