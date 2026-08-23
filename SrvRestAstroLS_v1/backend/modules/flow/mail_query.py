"""Safe Gmail query builder for Team360 Flow.

Provides a single contract for building safe Gmail search queries that
respect the historical cutoff protection. Never produces unsafe queries
that could include historical emails.
"""

from __future__ import annotations

DEFAULT_MAIL_CUTOFF_EPOCH = 1787239323
MIN_MAIL_CUTOFF_EPOCH = 1577836800
MAX_MAIL_CUTOFF_EPOCH = 1893456000


def _safe_cutoff_epoch(value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < MIN_MAIL_CUTOFF_EPOCH
        or value > MAX_MAIL_CUTOFF_EPOCH
    ):
        return DEFAULT_MAIL_CUTOFF_EPOCH
    return value


def build_mail_query(
    *,
    mail_after_cutoff: object,
    mail_cutoff_epoch: object,
) -> str:
    """Build a safe Gmail search query for Flow intake.

    Args:
        mail_after_cutoff: If True, apply the historical cutoff filter.
        mail_cutoff_epoch: Unix epoch timestamp for the cutoff. Only emails
            received AFTER this timestamp are eligible when cutoff is enabled.

    Returns:
        A Gmail search query string that is guaranteed safe.

    Safety guarantees:
        - When mail_after_cutoff=True: ALWAYS includes `after:<epoch>` filter.
          This selects emails AFTER the cutoff (excludes historical).
        - When mail_after_cutoff=False: Returns `in:inbox` without any
          historical filter (operator explicitly accepts all inbox).
        - NEVER produces `-after:` or `before:` filters that select historical.
        - NEVER falls back silently to unsafe queries.
    """
    # Only the explicit boolean False disables protection. Missing, null or
    # malformed values remain protected.
    if mail_after_cutoff is not False:
        cutoff_epoch = _safe_cutoff_epoch(mail_cutoff_epoch)
        # SAFE: `after:<epoch>` selects emails RECEIVED AFTER the cutoff.
        # This EXCLUDES historical emails (received before cutoff).
        return f"in:inbox after:{cutoff_epoch}"

    # Explicit demo/operator opt-out. Missing and invalid settings never reach
    # this branch.
    return "in:inbox"


def build_mail_query_from_settings(settings: dict) -> str:
    """Build query from operational settings dict.

    Expected keys in settings:
        - mail_after_cutoff (bool)
        - mail_cutoff_epoch (int)

    Falls back to safe defaults if keys are missing or invalid.
    """
    mail_after_cutoff = settings.get("mail_after_cutoff", True)
    mail_cutoff_epoch = settings.get(
        "mail_cutoff_epoch", DEFAULT_MAIL_CUTOFF_EPOCH
    )

    return build_mail_query(
        mail_after_cutoff=mail_after_cutoff,
        mail_cutoff_epoch=mail_cutoff_epoch,
    )
