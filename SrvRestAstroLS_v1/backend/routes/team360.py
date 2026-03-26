"""Team360 route placeholder."""


def get_team360_summary() -> dict[str, object]:
    """Return a minimal summary of the enabled modules."""
    return {
        "orchestrator": "team360_orquestador",
        "providers": ["gupshup", "mercadolibre"],
        "realtime": "agui-sse",
    }
