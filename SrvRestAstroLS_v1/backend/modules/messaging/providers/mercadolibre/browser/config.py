"""Mercado Libre browser lab configuration."""

from pathlib import Path

BASE_URL = "https://www.mercadolibre.com.ar/"
HOME_URL = BASE_URL

HEADLESS = False
DEFAULT_PROFILE_NAME = "default"

DEFAULT_TIMEOUT_MS = 10_000
NAVIGATION_TIMEOUT_MS = 30_000
MANUAL_LOGIN_TIMEOUT_SEC = 180
LOGIN_POLL_INTERVAL_SEC = 3

PROVIDER_DIR = Path(__file__).resolve().parent.parent
RUNTIME_DIR = PROVIDER_DIR / "runtime"
PROFILES_DIR = RUNTIME_DIR / "profiles"
STORAGE_STATE_DIR = RUNTIME_DIR / "storage_state"
SCREENSHOTS_DIR = RUNTIME_DIR / "screenshots"
