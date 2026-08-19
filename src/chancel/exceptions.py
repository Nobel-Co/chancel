"""Exceptions raised when scope isolation is violated or refused."""

from __future__ import annotations


class ChancelError(Exception):
    """Base class for every error this library raises deliberately."""


class ScopeViolation(ChancelError):
    """Raised by PolicyGate.authorize() on any deny.

    Carries enough structure for a caller (or a test) to identify exactly
    what was denied and why, without parsing a message string.
    """

    def __init__(
        self,
        reason: str,
        space_id: str | None,
        requested: tuple[str, ...],
        offending: tuple[str, ...],
    ) -> None:
        self.reason = reason
        self.space_id = space_id
        self.requested = requested
        self.offending = offending
        super().__init__(str(self))

    def __str__(self) -> str:
        offending = ", ".join(self.offending) if self.offending else "(none)"
        return (
            f"scope violation for space={self.space_id!r}: {self.reason} "
            f"(offending collections: {offending}; requested: {list(self.requested)})"
        )


class PromotionRefused(ChancelError):
    """Raised when promote_fact() is asked to promote mixed-provenance facts."""

    def __init__(self, reason: str, offending_ids: tuple[str, ...]) -> None:
        self.reason = reason
        self.offending_ids = offending_ids
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"promotion refused: {self.reason} (offending ids: {list(self.offending_ids)})"
