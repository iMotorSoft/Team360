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
    if not settings.kommo_login_url:
        raise SystemExit("Falta KOMMO_LOGIN_URL en .env o variables de entorno.")

    with browser_context("kommo") as (_, _, context, page):
        page.goto(settings.kommo_login_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        if settings.has_kommo_credentials:
            fill_first(
                page,
                [
                    "input[type='email']",
                    "input[name='email']",
                    "input[name='login']",
                    "input[autocomplete='username']",
                    "input[type='text']",
                ],
                settings.kommo_user,
                "usuario Kommo",
            )
            fill_first(
                page,
                [
                    "input[type='password']",
                    "input[name='password']",
                    "input[autocomplete='current-password']",
                ],
                settings.kommo_pass,
                "password Kommo",
            )
            click_first(
                page,
                [
                    "button[type='submit']",
                    "input[type='submit']",
                    "button:has-text('Log in')",
                    "button:has-text('Iniciar')",
                    "button:has-text('Ingresar')",
                    "button:has-text('Entrar')",
                ],
                "submit Kommo",
            )
            page.wait_for_timeout(5000)
        else:
            print("[login] sin credenciales en env; completar login manualmente si corresponde.")
            print("[hitl] Completar login Kommo en el navegador abierto y presionar ENTER aqui para guardar sesion.")
            input()

        wait_for_human_if_needed(page, "Kommo login")
        save_page_screenshot(page, screenshot_path("kommo_login_probe.png"))
        save_storage_state(context, "kommo")
        print(f"[login] URL final: {page.url}")


if __name__ == "__main__":
    main()
