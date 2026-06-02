class ConsoleBootstrapError(Exception):
    """Base exception for ConsoleBootstrap assembly errors."""


class WorkspaceNotFoundError(ConsoleBootstrapError):
    """Raised when the requested workspace does not exist."""


class UserNotFoundError(ConsoleBootstrapError):
    """Raised when the requested user does not exist in the workspace."""


class ConsolePermissionError(ConsoleBootstrapError):
    """Raised when a user cannot access the requested console context."""
