"""Health route placeholder."""

from globalVar import SERVICE_NAME, SERVICE_VERSION


def get_health() -> dict[str, str]:
    """Return a minimal health payload."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "version": SERVICE_VERSION,
    }
