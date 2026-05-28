from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from browser.playwright_context import (  # noqa: E402
    browser_context,
    click_first,
    fill_first,
    save_storage_state,
    wait_for_human_if_needed,
)
from browser.screenshots import save_page_screenshot  # noqa: E402
from config import get_settings, screenshot_path  # noqa: E402


def main() -> None:
    settings = get_settings()
    with browser_context("facebook") as (_, _, context, page):
        page.goto("https://www.facebook.com/login", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        if settings.has_facebook_credentials:
            fill_first(page, ["#email", "input[name='email']", "input[type='email']"], settings.facebook_user, "usuario Facebook")
            fill_first(page, ["#pass", "input[name='pass']", "input[type='password']"], settings.facebook_pass, "password Facebook")
            click_first(page, ["button[name='login']", "button[type='submit']", "input[type='submit']"], "submit Facebook")
            page.wait_for_timeout(5000)
        else:
            print("[login] sin credenciales en env; completar login manualmente si corresponde.")
            print("[hitl] Completar login Facebook en el navegador abierto y presionar ENTER aqui para guardar sesion.")
            input()

        wait_for_human_if_needed(page, "Facebook login")
        save_page_screenshot(page, screenshot_path("facebook_login_probe.png"))
        save_storage_state(context, "facebook")
        print(f"[login] URL final: {page.url}")


if __name__ == "__main__":
    main()
