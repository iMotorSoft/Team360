"""Placeholder entrypoint for the Team360 backend service."""

from routes.health import get_health


def main() -> None:
    """Run a minimal bootstrap check."""
    status = get_health()
    print(f"Team360 backend placeholder: {status}")


if __name__ == "__main__":
    main()
