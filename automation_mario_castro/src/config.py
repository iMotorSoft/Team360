from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = PROJECT_ROOT / "runtime"
SCREENSHOTS_DIR = RUNTIME_DIR / "screenshots"
INSPECT_DIR = RUNTIME_DIR / "inspect"
STORAGE_STATE_DIR = RUNTIME_DIR / "storage_state"
EXCEL_PATH = (
    PROJECT_ROOT.parent
    / "docs"
    / "clients"
    / "mario_castro"
    / "KPIs_CEO_Proyectos_Inmobiliarios_COMPLETO.xlsx"
)


def load_local_env(path: Path | None = None) -> None:
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    kommo_login_url: str
    kommo_user: str
    kommo_pass: str
    facebook_user: str
    facebook_pass: str
    headless: bool
    timeout_ms: int = 60000

    @property
    def has_kommo_credentials(self) -> bool:
        return bool(self.kommo_user and self.kommo_pass)

    @property
    def has_facebook_credentials(self) -> bool:
        return bool(self.facebook_user and self.facebook_pass)


def get_settings() -> Settings:
    load_local_env()
    return Settings(
        kommo_login_url=os.getenv("KOMMO_LOGIN_URL", "").strip(),
        kommo_user=os.getenv("KOMMO_USER", "").strip(),
        kommo_pass=os.getenv("KOMMO_PASS", "").strip(),
        facebook_user=os.getenv("FACEBOOK_USER", "").strip(),
        facebook_pass=os.getenv("FACEBOOK_PASS", "").strip(),
        headless=_bool_env("PLAYWRIGHT_HEADLESS", False),
    )


def ensure_runtime_dirs() -> None:
    for path in (RUNTIME_DIR, SCREENSHOTS_DIR, INSPECT_DIR, STORAGE_STATE_DIR):
        path.mkdir(parents=True, exist_ok=True)


def storage_state_path(name: str) -> Path:
    ensure_runtime_dirs()
    return STORAGE_STATE_DIR / f"{name}.json"


def inspect_path(name: str) -> Path:
    ensure_runtime_dirs()
    return INSPECT_DIR / name


def screenshot_path(name: str) -> Path:
    ensure_runtime_dirs()
    return SCREENSHOTS_DIR / name
