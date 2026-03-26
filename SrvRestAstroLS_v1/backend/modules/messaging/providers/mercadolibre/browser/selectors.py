"""Conservative selector sets for login smoke checks."""

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
