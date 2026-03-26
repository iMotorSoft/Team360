"""AG-UI route placeholder."""


def get_agui_status() -> dict[str, str]:
    """Return the structural AG-UI status."""
    return {
        "channel": "sse",
        "status": "pending-implementation",
    }
