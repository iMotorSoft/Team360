"""Inspection probe for Mercado Libre inbox DOM signals."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright

from ..browser.actions import (
    collect_inbox_inspection,
    maybe_save_storage_state,
    save_debug_screenshot,
    save_text_report,
)
from ..browser.config import DEFAULT_PROFILE_NAME, INSPECT_DIR
from ..browser.context import close_context, open_persistent_context
from ..browser.pages import ensure_inbox_loaded, maybe_open_inbox_candidates, stabilize_inbox
from ..browser.session_store import get_screenshot_path, get_storage_state_path


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(description="Inbox inspection smoke for Mercado Libre persistent browser sessions.")
    parser.add_argument("--profile", default=DEFAULT_PROFILE_NAME, help="Persistent browser profile name.")
    parser.add_argument("--timeout", type=int, default=90, help="Seconds to wait for inbox load signals.")
    return parser.parse_args()


def log(message: str) -> None:
    """Print a short progress message."""
    print(message, flush=True)


def _safe_name(value: str) -> str:
    """Keep generated runtime names filesystem-friendly."""
    return "".join(char if char.isalnum() or char in ("-", "_") else "_" for char in value).strip("_") or "default"


def _get_report_path(profile_name: str) -> Path:
    """Return a timestamped text report path for inbox inspection."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return INSPECT_DIR / f"inbox_inspect_{_safe_name(profile_name)}_{stamp}.txt"


def _format_report(profile_name: str, inspection: dict[str, object]) -> str:
    """Render a compact text report for manual selector tuning."""
    groups = inspection.get("groups", {})
    warnings = inspection.get("warnings", [])
    root_selector_counts = inspection.get("root_selector_counts", {})
    root_nodes = inspection.get("root_nodes", [])
    global_text_samples = inspection.get("global_text_samples", [])

    lines = [
        f"profile: {profile_name}",
        f"timestamp: {inspection.get('timestamp', '')}",
        f"final url: {inspection.get('final_url', '')}",
        f"page title: {inspection.get('page_title', '')}",
        f"ready_state: {inspection.get('ready_state', '')}",
        f"logged_in heuristic: {inspection.get('logged_in_heuristic', False)}",
        f"inbox_accessible heuristic: {inspection.get('inbox_accessible_heuristic', False)}",
        f"visible_threads heuristic: {inspection.get('visible_threads_heuristic', 0)}",
        f"empty_state heuristic: {inspection.get('empty_state_heuristic', False)}",
        f"iframe_count: {inspection.get('iframe_count', 0)}",
        f"anchor_count: {inspection.get('anchor_count', 0)}",
        f"button_count: {inspection.get('button_count', 0)}",
        f"body_text_length: {inspection.get('body_text_length', 0)}",
        f"body_html_length: {inspection.get('body_html_length', 0)}",
        "",
        "[root_selector_counts]",
    ]

    for selector, count in root_selector_counts.items():
        lines.append(f"{count:>3} | {selector}")

    lines.append("")
    lines.append("[root_nodes]")
    for node in root_nodes:
        lines.append(
            f"- tag={node.get('tag', '')} id={node.get('id', '')} role={node.get('role', '')} "
            f"child_count={node.get('child_count', 0)} text_length={node.get('text_length', 0)} "
            f"class={node.get('class_name', '')}"
        )

    lines.append("")
    lines.append("[global_text_samples]")
    for text in global_text_samples:
        lines.append(f"- {text}")

    for group_name, group_data in groups.items():
        lines.append("")
        lines.append(f"[{group_name}]")
        counts = group_data.get("counts", {})
        samples = group_data.get("samples", {})
        for selector, count in counts.items():
            lines.append(f"{count:>3} | {selector}")
        if samples:
            lines.append("samples:")
            for selector, texts in samples.items():
                lines.append(f"- {selector}")
                for text in texts:
                    lines.append(f"  - {text}")

    if warnings:
        lines.append("")
        lines.append("warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")

    return "\n".join(lines) + "\n"


def _log_group_summary(inspection: dict[str, object]) -> None:
    """Print only the non-zero selector counts per group."""
    groups = inspection.get("groups", {})
    for group_name, group_data in groups.items():
        counts = group_data.get("counts", {})
        matched = {selector: count for selector, count in counts.items() if count > 0}
        log(f"{group_name} matches {matched if matched else 'none'}")


def _log_root_summary(inspection: dict[str, object]) -> None:
    """Print only the non-zero generic root selector counts."""
    counts = inspection.get("root_selector_counts", {})
    matched = {selector: count for selector, count in counts.items() if count > 0}
    log(f"root candidates {matched if matched else 'none'}")


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
    """Execute the inbox inspection flow."""
    screenshot_path = get_screenshot_path(prefix=f"smoke_inbox_inspect_{profile_name}")
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
            log("abriendo inbox Mercado Libre")
            maybe_open_inbox_candidates(page, timeout_ms=max(timeout_sec, 1) * 1000)
            ensure_inbox_loaded(page, timeout_ms=2_000)
            stabilize_inbox(page)

            inspection = collect_inbox_inspection(page)
            report_text = _format_report(profile_name, inspection)
            save_text_report(report_path, report_text)
            log(f"final url {inspection.get('final_url', '')}")
            log(f"page title {inspection.get('page_title', '')}")
            log(f"ready_state {inspection.get('ready_state', '')}")
            log(f"body_text_length {inspection.get('body_text_length', 0)}")
            log(f"body_html_length {inspection.get('body_html_length', 0)}")
            log(f"iframe_count {inspection.get('iframe_count', 0)}")
            log(f"anchor_count {inspection.get('anchor_count', 0)}")
            log(f"button_count {inspection.get('button_count', 0)}")
            log(f"sesion activa heuristic {inspection.get('logged_in_heuristic', False)}")
            _log_root_summary(inspection)
            log(f"global text samples {'present' if inspection.get('global_text_samples') else 'none'}")
            _log_group_summary(inspection)
            if inspection.get("warnings"):
                log(f"warnings {inspection.get('warnings')}")
            log(f"report guardado en {report_path}")
            ok = bool(inspection.get("logged_in_heuristic"))
        except Exception as exc:
            log(f"error durante smoke inbox inspect: {exc}")
        finally:
            try:
                _save_artifacts(page, context, screenshot_path, storage_state_path)
            except Exception as exc:
                log(f"no se pudieron guardar artifacts: {exc}")
            close_context(context)

    log(f"final_url {inspection.get('final_url', '')}")
    log(f"page_title {inspection.get('page_title', '')}")
    log(f"ready_state {inspection.get('ready_state', '')}")
    log(f"visible_threads {inspection.get('visible_threads_heuristic', 0)}")
    log(f"empty_state {inspection.get('empty_state_heuristic', False)}")
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
