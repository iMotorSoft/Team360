"""Conservative selector sets for Mercado Libre smoke checks."""

# These are intentionally broad. The smoke only needs a reasonable signal.
LOGIN_ENTRY_SELECTORS: list[str] = [
    "a[data-link-id='login']",
    "a[href*='login']",
    "a[href*='registration']",
    "button[data-link-id='login']",
    "text=/ingresa|ingresar|inicia sesion|iniciar sesion/i",
]

# Account affordances vary by country and experiments, so keep this generic.
ACCOUNT_MENU_SELECTORS: list[str] = [
    "a[href*='/myml']",
    "a[href*='/perfil']",
    "button[aria-label*='cuenta' i]",
    "[data-testid='user-menu']",
    "text=/mi cuenta|perfil|mis compras/i",
]

LOGIN_URL_HINTS: tuple[str, ...] = (
    "/login",
    "/registration",
    "authentication",
)

ACCOUNT_URL_HINTS: tuple[str, ...] = (
    "/myml",
    "/perfil",
)

# Cookie names are a fallback only. They can change over time.
SESSION_COOKIE_NAMES: tuple[str, ...] = (
    "orguseridp",
    "ssid",
)

INBOX_URL_HINTS: tuple[str, ...] = (
    "/messages",
    "/inbox",
    "/preguntas",
)

# Inbox DOM changes often, so these stay broad on purpose.
INBOX_CONTAINER_SELECTORS: list[str] = [
    "[data-testid='conversation-list']",
    "[data-testid*='conversation']",
    "[class*='conversation-list']",
    "[class*='messages']",
    "[class*='inbox']",
]

INBOX_THREAD_SELECTORS: list[str] = [
    "[data-testid*='conversation-item']",
    "[data-testid*='thread']",
    "[class*='conversation-item']",
    "[class*='thread-item']",
    "a[href*='/messages/']",
]

INBOX_DENIED_HINT_SELECTORS: list[str] = [
    "text=/inicia sesion|inicia sesión|ingresa|ingresar/i",
    "text=/no tienes permiso|no tenes permiso|acceso denegado|inicia sesion para ver tus mensajes/i",
    "a[href*='login']",
    "button[data-link-id='login']",
]

INBOX_EMPTY_STATE_SELECTORS: list[str] = [
    "text=/no hay mensajes|no tienes mensajes|no tenes mensajes|sin mensajes|sin conversaciones/i",
    "text=/aun no tienes conversaciones|aún no tienes conversaciones/i",
]

INBOX_SELECTOR_GROUPS: dict[str, list[str]] = {
    "inbox_container": INBOX_CONTAINER_SELECTORS,
    "thread_items": INBOX_THREAD_SELECTORS,
    "empty_state": INBOX_EMPTY_STATE_SELECTORS,
    "login_or_denied": INBOX_DENIED_HINT_SELECTORS,
}

# Questions page signals are intentionally broad and should be tuned with reports.
QUESTIONS_LIST_CONTAINER_SELECTORS: list[str] = [
    "[data-testid*='question-list']",
    "[data-testid*='questions-list']",
    "[class*='question-list']",
    "[class*='questions-list']",
    "[class*='questions__list']",
    "[class*='question-results']",
    "main [role='list']",
    "main ul",
    "main table",
]

QUESTIONS_ITEM_SELECTORS: list[str] = [
    ".sc-item",
    ".sc-item__active",
    ".andes-card.sc-item",
    ".sc-question-container",
    ".andes-list__item-content",
    "[data-testid*='question-item']",
    "[data-testid*='question-row']",
    "[data-testid*='question-card']",
    "[class*='question-item']",
    "[class*='question-row']",
    "[class*='question-card']",
    "[class*='questions-list'] li",
    "[class*='question-list'] li",
    "main tbody tr",
    "main article",
    "main li",
]

QUESTIONS_EMPTY_STATE_SELECTORS: list[str] = [
    "text=/no tienes preguntas|no tenes preguntas|sin preguntas/i",
    "text=/aun no tienes preguntas|aún no tienes preguntas/i",
    "text=/todavia no recibiste preguntas|todavía no recibiste preguntas/i",
    "text=/cuando recibas preguntas|cuando tengas preguntas/i",
]

QUESTIONS_FILTER_SELECTORS: list[str] = [
    "button",
    "[role='button']",
    "[role='tab']",
    "a",
]

QUESTIONS_STATUS_HINT_SELECTORS: list[str] = [
    "[data-testid*='status']",
    "[data-testid*='badge']",
    "[class*='status']",
    "[class*='badge']",
    "span",
    "small",
]

QUESTIONS_CTA_SELECTORS: list[str] = [
    "button",
    "[role='button']",
    "a",
]
