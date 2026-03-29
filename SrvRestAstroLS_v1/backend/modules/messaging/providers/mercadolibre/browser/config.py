"""Mercado Libre browser lab configuration."""

from pathlib import Path

BASE_URL = "https://www.mercadolibre.com.ar/"
HOME_URL = BASE_URL
ACCOUNT_SUMMARY_URL = "https://myaccount.mercadolibre.com.ar/summary"
QUESTIONS_URL = "https://www.mercadolibre.com.ar/preguntas/vendedor"
INBOX_URL = f"{BASE_URL}messages"
INBOX_CANDIDATE_URLS: tuple[str, ...] = (
    INBOX_URL,
    f"{BASE_URL}myml/messages",
    f"{BASE_URL}inbox",
)
HOME_DISCOVERY_KEYWORDS: tuple[str, ...] = (
    "mensaje",
    "mensajes",
    "preguntar",
    "pregunta",
    "preguntas",
    "venta",
    "ventas",
    "compra",
    "compras",
    "notificacion",
    "notificaciones",
    "inbox",
    "message",
    "messages",
    "question",
    "questions",
    "sale",
    "sales",
    "account",
    "cuenta",
    "perfil",
    "mi cuenta",
    "myml",
)
SUMMARY_DISCOVERY_KEYWORDS: tuple[str, ...] = (
    "mensaje",
    "mensajes",
    "preguntar",
    "preguntas",
    "venta",
    "ventas",
    "vendedor",
    "vender",
    "publicacion",
    "publicaciones",
    "producto",
    "productos",
    "compra",
    "compras",
    "notificacion",
    "notificaciones",
    "cuenta",
    "perfil",
    "ayuda",
    "message",
    "messages",
    "question",
    "questions",
    "sale",
    "sales",
    "selling",
    "seller",
    "listing",
    "listings",
    "product",
    "products",
    "account",
    "profile",
    "help",
    "myml",
)

QUESTIONS_DISCOVERY_KEYWORDS: tuple[str, ...] = (
    "pregunta",
    "preguntas",
    "responder",
    "respuesta",
    "comprador",
    "cliente",
    "mensaje",
    "mensajes",
    "producto",
    "publicacion",
    "publicaciones",
    "venta",
    "ventas",
    "filtro",
    "pendientes",
    "respondidas",
    "sin responder",
    "question",
    "questions",
    "answer",
    "buyer",
    "customer",
    "product",
    "listing",
    "sale",
    "sales",
)
WIZARD_KEYWORDS: tuple[str, ...] = (
    "entendido",
    "siguiente",
    "omitir",
    "finalizar",
    "bienvenido",
    "guia",
    "tutorial",
    "recorrido",
    "primera publicacion",
    "empeza a vender",
    "empezá a vender",
    "completa tu perfil",
    "onboarding",
    "wizard",
    "tour",
    "guide",
    "welcome",
    "start selling",
)

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
INSPECT_DIR = RUNTIME_DIR / "inspect"
