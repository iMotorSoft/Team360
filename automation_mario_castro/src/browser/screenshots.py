from __future__ import annotations

from pathlib import Path


def save_page_screenshot(page, path: Path, full_page: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full_page)
    print(f"[screenshot] {path}")
    return path
