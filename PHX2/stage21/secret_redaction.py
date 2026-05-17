"""Stage 21 secret redaction and fingerprinting helpers.

The Stage 21 contract is that no secret value -- API key, RPC URL,
webhook URL, bot token, chat id -- ever appears in ``repr``,
``str``, logs, manifests, telemetry, errors, exception messages,
snapshots, fixtures, or committed artifacts. Every Stage 21 module
outside ``PHX2/stage21/config.py`` receives ``SecretRef`` instances
instead of raw values; ``SecretRef`` carries only the presence flag,
the optional length, and the truncated sha256 fingerprint.

This module is the single source of truth for that mapping. The
``fingerprint`` helper accepts ``Optional[str]`` and returns a
fingerprint string for present values, or ``""`` for ``None`` /
empty inputs (so the empty / missing case still produces a
deterministic, non-secret value the public summary can show).

The helpers here intentionally do NOT log, persist, or echo the
raw value back. The only exposure of the raw value happens inside
``PHX2/stage21/config.py``, which constructs a ``SecretRef`` from
it immediately and then drops the local reference.
"""

from __future__ import annotations

import hashlib
from typing import NamedTuple, Optional

from PHX2.stage21.constants import (
    REDACTED_VALUE_SENTINEL,
    SECRET_FINGERPRINT_HEX_LENGTH,
)
from PHX2.stage21.errors import Stage21SecretError
from PHX2.stage21.constants import Stage21ErrorCode


class SecretRef(NamedTuple):
    """Public-safe reference to a Stage 21 secret value.

    Stores only:
      * ``name``: the env-var name (or other non-secret label) that
        identifies the secret slot. Non-secret by definition.
      * ``present``: True when the underlying value was non-empty.
      * ``length``: byte length of the underlying value (``0`` when
        absent). Length itself is a side-channel-light datum;
        Stage 21 emits it so the operator can sanity-check rotation
        / typos without seeing the value.
      * ``fingerprint``: ``sha256(value).hexdigest()[:12]`` when
        present, otherwise the empty string. Stage 21.1 deliberately
        uses a 12-hex-char prefix; collisions are tolerable for
        operator-visible fingerprinting and 12 chars keep the public
        summary compact.

    The ``__repr__`` / ``__str__`` of ``SecretRef`` is the public
    summary view, NOT the raw value. ``SecretRef`` has no field for
    the raw value; once construction is done the value cannot be
    recovered. Pickling / round-tripping reproduces only the
    public-safe fields.

    Note: webhook URLs, bot tokens, and chat IDs are all
    secret-class in Stage 21; every such value is held in a
    ``SecretRef`` regardless of whether the upstream type is "URL"
    or "ID".
    """

    name: str
    present: bool
    length: int
    fingerprint: str

    def public_summary(self) -> dict[str, object]:
        """Return the manifest/telemetry-safe summary mapping.

        Used by Stage 21 writers that emit a non-secret summary of
        the loaded config. Keys are stable across runs; values are
        always non-secret.
        """
        return {
            "name": self.name,
            "present": self.present,
            "length": self.length,
            "fingerprint": self.fingerprint,
        }


def compute_fingerprint(value: Optional[str]) -> str:
    """Return the truncated sha256 fingerprint for ``value``.

    The fingerprint is ``sha256(value.encode("utf-8"))
    .hexdigest()[:SECRET_FINGERPRINT_HEX_LENGTH]``.

    Returns the empty string when ``value`` is ``None`` or the empty
    string (so the missing case has a deterministic, non-secret
    representation).

    Raises ``Stage21SecretError`` with code ``E2103`` if ``value``
    is not ``None`` and not a ``str`` (e.g. bytes, int). Callers
    should pass ``str`` values directly from ``os.environ`` reads.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        raise Stage21SecretError(
            Stage21ErrorCode.E2103,
            detail=(
                "compute_fingerprint expected Optional[str] but got "
                f"{type(value).__name__}"
            ),
        )
    if value == "":
        return ""
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return digest[:SECRET_FINGERPRINT_HEX_LENGTH]


def build_secret_ref(name: str, value: Optional[str]) -> SecretRef:
    """Build a ``SecretRef`` from a single env-var slot.

    The function is the only public way to construct a ``SecretRef``
    that carries a real fingerprint. ``name`` is the non-secret
    label (typically the env-var name). ``value`` is consumed
    locally and not stored anywhere on the returned ``SecretRef``.

    ``Stage21SecretError`` (E2103) is raised when ``value`` is the
    wrong type. An empty / ``None`` value produces a
    ``present=False`` ref with a zero length and an empty
    fingerprint.
    """
    if value is None or value == "":
        return SecretRef(
            name=name,
            present=False,
            length=0,
            fingerprint="",
        )
    fingerprint = compute_fingerprint(value)
    length = len(value.encode("utf-8"))
    return SecretRef(
        name=name,
        present=True,
        length=length,
        fingerprint=fingerprint,
    )


def redact_for_public(value: Optional[str]) -> str:
    """Render a public-safe placeholder for ``value``.

    Returns ``REDACTED_VALUE_SENTINEL`` when ``value`` is present
    (non-empty), and the empty string when ``value`` is ``None`` or
    empty. The function never echoes the raw value.

    Used by config / telemetry summary builders that need a textual
    placeholder rather than a full ``SecretRef``. The sentinel
    string is locked in ``PHX2.stage21.constants`` so the public
    summary's textual shape stays stable across runs.
    """
    if value is None or value == "":
        return ""
    return REDACTED_VALUE_SENTINEL


def fingerprint_matches(value: Optional[str], fingerprint: str) -> bool:
    """Return True iff ``value`` hashes to ``fingerprint``.

    Used by tests that verify the fingerprint helper is
    deterministic across runs. The function itself never logs
    ``value`` and never echoes it back.

    Returns False when either argument is empty (the "no
    fingerprint" case) so callers can use the helper as a strict
    presence-and-match check.
    """
    if not fingerprint:
        return False
    return compute_fingerprint(value) == fingerprint


__all__ = [
    "SecretRef",
    "build_secret_ref",
    "compute_fingerprint",
    "fingerprint_matches",
    "redact_for_public",
]
