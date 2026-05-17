"""Stage 21 typed allowlist parser and model.

Stage 21 dispatches only to operator-controlled targets. The
allowlist model declared here captures the set of allowed
recipient identifiers (e.g. operator IDs); 21.1 ships only the
parser + the typed record. No real dispatch checks against the
allowlist yet -- that wiring belongs to the Stage 21.4 transport
sub-stage.

Fail-closed semantics:
  * An empty allowlist parses to an ``OperatorAllowlist`` with
    ``recipients=()`` and ``fail_closed=True``.
  * A future dispatcher MUST reject any send when ``fail_closed``
    is true. Stage 21.1's tests assert the parser produces the
    fail-closed shape for empty / whitespace-only input; the
    dispatcher itself is later-stage scope.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

from PHX2.stage21.constants import Stage21ErrorCode
from PHX2.stage21.errors import Stage21ConfigError


class OperatorAllowlist(NamedTuple):
    """Frozen typed allowlist of operator recipient identifiers.

    Fields:
      * ``recipients``: lexicographically sorted, deduplicated tuple
        of recipient identifiers. Empty tuple when no recipients
        are configured.
      * ``fail_closed``: True when the allowlist is empty. The
        dispatcher contract MUST treat ``fail_closed=True`` as
        "reject every candidate send" so a misconfigured / unset
        allowlist defaults to silence rather than to wide dispatch.
    """

    recipients: tuple[str, ...]
    fail_closed: bool

    def is_empty(self) -> bool:
        """Return True when the allowlist contains no recipients."""
        return len(self.recipients) == 0

    def contains(self, recipient: str) -> bool:
        """Return True iff ``recipient`` is in the allowlist.

        The check is exact-match against the parsed identifier. The
        allowlist contains identifiers in their canonical
        (stripped) form; callers should pass the canonical form
        too.
        """
        return recipient in self.recipients


def _validate_token(token: str) -> str:
    """Return the canonical form of an allowlist token, or raise.

    Stage 21.1 accepts non-empty tokens that contain no commas, no
    leading / trailing whitespace, and no newlines. The
    canonical form is the input verbatim once stripped. The check
    rejects any token containing characters that would prevent
    deterministic round-trip through the env-var parser.
    """
    stripped = token.strip()
    if not stripped:
        raise Stage21ConfigError(
            Stage21ErrorCode.E2105,
            detail="allowlist token was empty after stripping",
        )
    if "," in stripped:
        raise Stage21ConfigError(
            Stage21ErrorCode.E2105,
            detail=(
                "allowlist token contains comma; parser splits on "
                "comma so the token cannot survive a round-trip"
            ),
        )
    if "\n" in stripped or "\r" in stripped:
        raise Stage21ConfigError(
            Stage21ErrorCode.E2105,
            detail="allowlist token contains newline characters",
        )
    return stripped


def parse_allowlist(raw: Optional[str]) -> OperatorAllowlist:
    """Parse a comma-separated env-var value into an ``OperatorAllowlist``.

    ``raw=None`` and ``raw=""`` both produce the empty,
    fail-closed allowlist. Tokens are split on commas, stripped of
    surrounding whitespace, validated, and deduplicated. The
    returned tuple is sorted lexicographically so the parser is
    fully deterministic.

    Raises ``Stage21ConfigError`` (E2105) when an individual token
    fails validation. ``Stage21ConfigError`` (E2102) is reserved
    for the config module to raise when the broader allowlist
    config value (e.g. wrong type) is invalid; tokens themselves
    are an E2105 concern.
    """
    if raw is None:
        return OperatorAllowlist(recipients=(), fail_closed=True)
    stripped = raw.strip()
    if not stripped:
        return OperatorAllowlist(recipients=(), fail_closed=True)
    pieces = [piece for piece in stripped.split(",")]
    canonical: set[str] = set()
    for piece in pieces:
        # Validate each non-empty piece. Stripped-empty pieces
        # produced by stray commas (e.g. "a,,b") are tolerated and
        # skipped rather than raising; the canonical set is the
        # only output that matters.
        if piece.strip() == "":
            continue
        canonical.add(_validate_token(piece))
    recipients = tuple(sorted(canonical))
    return OperatorAllowlist(
        recipients=recipients,
        fail_closed=len(recipients) == 0,
    )


def build_allowlist_from_sequence(
    items: Sequence[str],
) -> OperatorAllowlist:
    """Build an ``OperatorAllowlist`` from an explicit sequence.

    Useful for tests and for non-env-driven construction. Each
    element is validated and canonicalized exactly as in
    ``parse_allowlist``. Duplicates are dropped.
    """
    canonical: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise Stage21ConfigError(
                Stage21ErrorCode.E2105,
                detail=(
                    "build_allowlist_from_sequence expected str items; "
                    f"got {type(item).__name__}"
                ),
            )
        # Skip empty / whitespace-only items rather than raising,
        # mirroring the parser tolerance.
        if item.strip() == "":
            continue
        canonical.add(_validate_token(item))
    recipients = tuple(sorted(canonical))
    return OperatorAllowlist(
        recipients=recipients,
        fail_closed=len(recipients) == 0,
    )


__all__ = [
    "OperatorAllowlist",
    "build_allowlist_from_sequence",
    "parse_allowlist",
]
