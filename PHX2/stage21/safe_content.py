"""Stage 21.2 remediation: shared safe-content predicate.

This module is the single canonical home of the Stage 21.2
remediation predicate. It is the only new production module
introduced by the remediation (per R2 of the locked remediation
prompt).

Design summary
==============

Stage 21.2's Codex audit found that Stage 21.2 accepted arbitrary
``run_id`` / ``mint`` / payload string values at every boundary,
including values containing URLs, webhook tokens, or forbidden
routing tokens (Critical: PoC produced manifest artifacts
containing URL-shaped values pointing at a fake operator-only
``public_dispatch`` endpoint). The
remediation replaces ad-hoc per-module string checks with a
single predicate applied at six explicit boundaries
(per R11 of the locked remediation prompt), plus simulator-entry
and writer-entry defense-in-depth.

The predicate has three public kinds (locked at three, per R3 of
the locked remediation prompt; ISO_TIMESTAMP and FREEFORM_TEXT
were intentionally dropped):

  * ``SHORT_LABEL``      -- snake-case-ish labels for non-id strings.
                            ``[A-Za-z0-9_]``, max 64.
  * ``SHORT_IDENTIFIER`` -- snake_case + hyphen identifiers.
                            ``[A-Za-z0-9_-]``, max 128.
  * ``TOKEN_ADDRESS``    -- base58 mint / token addresses
                            (Solana shape). 32..64 chars,
                            ``[1-9A-HJ-NP-Za-km-z]``. Forward-
                            looking: Stage 21.2 fake fixtures use
                            the ``mint`` key which routes to
                            SHORT_LABEL. TOKEN_ADDRESS becomes
                            active once a Stage 21.3+ adapter
                            introduces real on-chain mint
                            addresses keyed under
                            ``token_address`` / ``token_mint``.

Beyond the three public kinds, the per-key handlers in the
payload-dict validator route values for these special key sets to
non-enum validators:

  * ``_TIMESTAMP_KEYS``  -- ``generated_at_utc_iso``,
                            ``captured_at_utc``, ``observed_at_utc``
                            are validated against the exact
                            ``_RFC3339_UTC_RE`` regex (S2
                            adjudication). The forbidden-substring
                            scan still applies.
  * ``_HASH_KEYS``       -- ``payload_hash``,
                            ``recomputed_payload_hash`` are
                            validated as exactly 64 lowercase hex
                            chars (R8a).
  * ``_TOKEN_ADDRESS_KEYS`` -- routes values for ``token_address``
                            and ``token_mint`` keys through the
                            TOKEN_ADDRESS predicate (R9 / S5).
  * ``_SHORT_IDENTIFIER_KEYS`` -- routes values for ``run_id``,
                            ``candidate_id``, ``source_event_id``,
                            ``event_id`` through the
                            SHORT_IDENTIFIER predicate (R9).

Exemption sets
==============

Two key sets are explicitly EXEMPT from the default
SHORT_LABEL/SHORT_IDENTIFIER predicate but are still counted in
the node-count budget:

  * Marker-key exempt (S1): passed by the caller via the
    ``exempt_keys`` parameter on
    ``validate_safe_payload_dict``. The transport-capture
    boundary (R11e) and writer-entry guards pass the locked
    ``PING_PAYLOAD_REQUIRED_MARKER_KEYS`` set (5 keys: ``stage``,
    ``visibility``, ``operator_only``, ``live_mode``,
    ``dispatch_target``). Marker values are already exact-equality
    enforced by ``assert_private_preview_markers`` which is
    strictly stricter than any predicate, so re-validating them
    would be redundant and the locked stage marker ``"21.2"``
    contains a literal ``.`` that would otherwise trip
    SHORT_LABEL.

  * Rendered-text exempt (S3): ``summary_text`` and ``body_text``
    are deterministic template renders over already-validated
    candidate fields (chain of trust). The artifact substring
    scan provides defense-in-depth coverage. The exact set is
    pinned at exactly two entries via
    ``RENDERED_TEXT_EXEMPT_KEYS``; adding a new exemption
    requires updating the structural test
    ``test_payload_validator_exemption_set_is_locked``.

The locked total exemption set is **10 keys** (5 marker + 3
timestamp + 2 rendered-text). The structural test in
``PHX2/tests/stage21/test_stage21_2_safe_content.py`` pins this
exact set.

Forbidden substrings
====================

The remediation locks an exactly-11-entry forbidden substring
set in ``PHX2.stage21.constants.FORBIDDEN_SUBSTRINGS``. The set
is intentionally narrow:

  http-scheme-prefix, https-scheme-prefix, colon-slash-slash,
  webhook, api_key, secret, password, credential,
  public_dispatch, paid_dispatch, subscriber

(URL-scheme strings are spelled out at runtime in
``constants.py`` so the literal URL substrings never appear in
any production source file.)

Notably absent: ``token``, ``auth``, ``bearer``. The literal key
name ``token`` is forbidden at the payload-key level (the bare
key is reserved for credential material); values containing
``token`` are forbidden ONLY for credential-like or routing-like
keys, while safe domain labels ``token_address`` / ``token_mint``
are explicitly whitelisted via
``KNOWN_SAFE_DOMAIN_TOKEN_KEYS``.

For continuity, ``PHX2/stage21/normalized_events.py`` keeps a
wider supplemental key-rejection list as a Stage 21.2-local
supplement on top of this shared predicate; see that module's
docstring for the rationale.

TOKEN_ADDRESS (forward-looking)
================================

TOKEN_ADDRESS is implemented per R6 of the locked remediation
prompt and fully unit-tested. No production caller in Stage 21.2
uses TOKEN_ADDRESS validation: fake fixtures use the key
``mint`` (length 14, contains underscore) which routes to
SHORT_LABEL. TOKEN_ADDRESS becomes active when a Stage 21.3+
real-provider adapter starts emitting on-chain mint addresses
under the ``token_address`` or ``token_mint`` keys.

Redaction (R10)
===============

Every violation raises ``Stage21Error`` with a sanitized detail
string of the form::

    field=<field_name> kind=<kind> code=<E2xxx>
        length=<n> redacted=<first4>...<last2> [matched=<sub>]

The redaction format is locked at first-4 + literal ``...`` +
last-2 so the full offending value never enters the detail. The
upstream Stage 21.1 ``sanitize_detail`` further protects against
URL / long-token leaks, but the redaction format above does not
trigger that sanitizer for sensible-length values because the
literal ``.`` characters break the candidate run-length match.

Failure model
=============

Every violation raises ``Stage21Error`` with one of:

  * E2150 safe_string_violation_empty
  * E2151 safe_string_violation_too_long
  * E2152 safe_string_violation_disallowed_chars
  * E2153 safe_string_violation_forbidden_substring
  * E2154 safe_string_violation_control_char
  * E2155 safe_string_violation_invalid_base58
  * E2156 payload_too_deeply_nested
  * E2157 payload_too_many_nodes
  * E2158 payload_unsupported_value_type
  * E2170 payload_hash_mismatch_at_capture (raised by the
          fake-transport capture boundary, not by this module)

There is no "warn and continue", no "redact and proceed", no
silent coercion. Violations fail closed.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Mapping, Optional

from PHX2.stage21.constants import (
    FORBIDDEN_SUBSTRINGS,
    KNOWN_SAFE_DOMAIN_TOKEN_KEYS,
    Stage21ErrorCode,
)
from PHX2.stage21.errors import Stage21Error


# URL-scheme fragments used by the TOKEN_ADDRESS validator. Built
# by filtering the locked FORBIDDEN_SUBSTRINGS for the scheme-prefix
# / scheme-suffix shapes so the literal URL substrings never need to
# appear in this source file (see
# ``test_no_url_literals_in_production_source``).
_TOKEN_ADDRESS_URL_FRAGMENTS: tuple[str, ...] = tuple(
    sub for sub in FORBIDDEN_SUBSTRINGS if sub.endswith(":" + "//")
)


# ---------------------------------------------------------------------------
# Locked character classes + length bounds
# ---------------------------------------------------------------------------


_SHORT_LABEL_CHAR_RE: "re.Pattern[str]" = re.compile(r"^[A-Za-z0-9_]+$")
_SHORT_LABEL_MAX_LENGTH: int = 64

# SHORT_IDENTIFIER: [A-Za-z0-9_-] only. Colon and period from the
# original R8 char-set were dropped per C2 adjudication; timestamps
# are validated separately via _RFC3339_UTC_RE.
_SHORT_IDENTIFIER_CHAR_RE: "re.Pattern[str]" = re.compile(r"^[A-Za-z0-9_\-]+$")
_SHORT_IDENTIFIER_MAX_LENGTH: int = 128

# Bitcoin/Solana base58 alphabet: 1-9 A-H J-N P-Z a-k m-z (no 0, O,
# I, l).
_BASE58_CHAR_RE: "re.Pattern[str]" = re.compile(
    r"^[1-9A-HJ-NP-Za-km-z]+$"
)
_TOKEN_ADDRESS_MIN_LENGTH: int = 32
_TOKEN_ADDRESS_MAX_LENGTH: int = 64

# Exact 64-char lowercase hex (sha256 hexdigest).
_PAYLOAD_HASH_RE: "re.Pattern[str]" = re.compile(r"^[a-f0-9]{64}$")

# Exact RFC3339 UTC with literal Z suffix and optional fractional
# seconds (1..6 digits).
_RFC3339_UTC_RE: "re.Pattern[str]" = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$"
)

# Payload-dict nesting + node-count bounds (R9).
_PAYLOAD_MAX_DEPTH: int = 8
_PAYLOAD_MAX_NODES: int = 1024


# ---------------------------------------------------------------------------
# Key-aware kind routing (R9)
# ---------------------------------------------------------------------------


_TIMESTAMP_KEYS: frozenset[str] = frozenset({
    "generated_at_utc_iso",
    "captured_at_utc",
    "observed_at_utc",
})

_HASH_KEYS: frozenset[str] = frozenset({
    "payload_hash",
    "recomputed_payload_hash",
})

_TOKEN_ADDRESS_KEYS: frozenset[str] = frozenset({
    "token_address",
    "token_mint",
})

_SHORT_IDENTIFIER_KEYS: frozenset[str] = frozenset({
    "run_id",
    "candidate_id",
    "source_event_id",
    "event_id",
})

# Locked rendered-text exemption (S3). Adding to this set requires
# updating the structural exemption test.
RENDERED_TEXT_EXEMPT_KEYS: frozenset[str] = frozenset({
    "summary_text",
    "body_text",
})

# Default (empty) marker-key exempt set. Callers pass the locked
# PING_PAYLOAD_REQUIRED_MARKER_KEYS via the ``exempt_keys``
# parameter at the transport-capture boundary and at writer entry.
MARKER_EXEMPT_KEYS_DEFAULT: frozenset[str] = frozenset()


# Routing-/credential-context "token" check (R5/R7/R8).
# The bare key name "token" is forbidden everywhere. Compound keys
# of the form *_token, token_* are forbidden when they fall outside
# the known-safe domain set below.
_SAFE_DOMAIN_TOKEN_KEYS_SET: frozenset[str] = frozenset(
    KNOWN_SAFE_DOMAIN_TOKEN_KEYS
)


# ---------------------------------------------------------------------------
# Public enum
# ---------------------------------------------------------------------------


class SafeStringKind(str, Enum):
    """Locked Stage 21.2 safe-string kinds (exactly three, per R3)."""

    SHORT_LABEL = "SHORT_LABEL"
    SHORT_IDENTIFIER = "SHORT_IDENTIFIER"
    TOKEN_ADDRESS = "TOKEN_ADDRESS"


# ---------------------------------------------------------------------------
# Redaction (R10)
# ---------------------------------------------------------------------------


def _redacted_value(value: str) -> str:
    """Return first-4 + ``...`` + last-2 redacted form.

    Locked format. Values of length 6 or less are rendered as
    ``*`` * len(value) so the full short value never appears.
    """
    if len(value) <= 6:
        return "*" * len(value)
    return value[:4] + "..." + value[-2:]


def _raise_violation(
    *,
    code: Stage21ErrorCode,
    field_name: str,
    kind: str,
    value: object,
    extra: str = "",
) -> None:
    """Raise ``Stage21Error`` with the locked detail format (R10).

    The detail format is space-separated ``label value`` pairs.
    The ``=`` character is intentionally avoided: it sits inside
    the Stage 21.1 ``sanitize_detail`` candidate character class
    ``[A-Za-z0-9+/=_-]``, which would otherwise treat
    ``field=foo`` as a single 9+ char candidate and redact the
    field name. Using spaces lets each label and value pass
    through the sanitizer as a short identifier-shape word.

    The redaction format for the offending value is locked at
    first-4 + literal ``...`` + last-2 so the full value never
    enters the detail; the literal ``.`` characters break the
    sanitize_detail candidate run-length match for typical
    lengths.
    """
    if isinstance(value, str):
        length = len(value)
        redacted = _redacted_value(value)
    else:
        length = -1
        redacted = "<non-str>"
    detail_parts = [
        f"field {field_name}",
        f"kind {kind}",
        f"code {code.value}",
        f"length {length}",
        f"redacted {redacted}",
    ]
    if extra:
        detail_parts.append(extra)
    detail = " ".join(detail_parts)
    raise Stage21Error(code, detail=detail)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _has_control_chars(value: str) -> bool:
    """Return True iff ``value`` contains any ASCII control char."""
    for ch in value:
        cp = ord(ch)
        if cp < 32 or cp == 127:
            return True
    return False


def _matched_forbidden_substring(value: str) -> Optional[str]:
    """Return the first forbidden substring matched (case-insensitive)."""
    lower = value.lower()
    for sub in FORBIDDEN_SUBSTRINGS:
        if sub in lower:
            return sub
    return None


# ---------------------------------------------------------------------------
# Per-kind validators
# ---------------------------------------------------------------------------


def validate_safe_string(
    value: object,
    *,
    kind: SafeStringKind,
    field_name: str,
) -> None:
    """Validate ``value`` against ``kind``.

    Fail-closed semantics. Raises ``Stage21Error`` with one of:
      E2158 unsupported value type (non-str)
      E2150 empty
      E2154 control char
      E2151 too long
      E2152 disallowed chars (char-class mismatch)
      E2153 forbidden substring (FORBIDDEN_SUBSTRINGS hit)
      E2155 invalid base58 (TOKEN_ADDRESS-only)
    """
    if not isinstance(value, str):
        _raise_violation(
            code=Stage21ErrorCode.E2158,
            field_name=field_name,
            kind=kind.value,
            value=value,
            extra=f"actual_type {type(value).__name__}",
        )
    if value == "":
        _raise_violation(
            code=Stage21ErrorCode.E2150,
            field_name=field_name,
            kind=kind.value,
            value=value,
        )
    if _has_control_chars(value):
        _raise_violation(
            code=Stage21ErrorCode.E2154,
            field_name=field_name,
            kind=kind.value,
            value=value,
        )
    if kind is SafeStringKind.SHORT_LABEL:
        if len(value) > _SHORT_LABEL_MAX_LENGTH:
            _raise_violation(
                code=Stage21ErrorCode.E2151,
                field_name=field_name,
                kind=kind.value,
                value=value,
                extra=f"max {_SHORT_LABEL_MAX_LENGTH}",
            )
        # Forbidden-substring check runs BEFORE the char-set check
        # so URL-shaped values (which would also trip the char-set
        # check for SHORT_LABEL) surface as E2153
        # forbidden_substring rather than the less-specific
        # E2152 disallowed_chars. This matches the Codex PoC
        # reproduction tests' expectation that URL-laced fields
        # are rejected with E2153.
        sub = _matched_forbidden_substring(value)
        if sub is not None:
            _raise_violation(
                code=Stage21ErrorCode.E2153,
                field_name=field_name,
                kind=kind.value,
                value=value,
                extra=f"matched {sub}",
            )
        if not _SHORT_LABEL_CHAR_RE.match(value):
            _raise_violation(
                code=Stage21ErrorCode.E2152,
                field_name=field_name,
                kind=kind.value,
                value=value,
            )
    elif kind is SafeStringKind.SHORT_IDENTIFIER:
        if len(value) > _SHORT_IDENTIFIER_MAX_LENGTH:
            _raise_violation(
                code=Stage21ErrorCode.E2151,
                field_name=field_name,
                kind=kind.value,
                value=value,
                extra=f"max {_SHORT_IDENTIFIER_MAX_LENGTH}",
            )
        # Forbidden-substring check runs BEFORE the char-set
        # check (same rationale as SHORT_LABEL above).
        sub = _matched_forbidden_substring(value)
        if sub is not None:
            _raise_violation(
                code=Stage21ErrorCode.E2153,
                field_name=field_name,
                kind=kind.value,
                value=value,
                extra=f"matched {sub}",
            )
        if not _SHORT_IDENTIFIER_CHAR_RE.match(value):
            _raise_violation(
                code=Stage21ErrorCode.E2152,
                field_name=field_name,
                kind=kind.value,
                value=value,
            )
    elif kind is SafeStringKind.TOKEN_ADDRESS:
        if (
            len(value) < _TOKEN_ADDRESS_MIN_LENGTH
            or len(value) > _TOKEN_ADDRESS_MAX_LENGTH
        ):
            _raise_violation(
                code=Stage21ErrorCode.E2151,
                field_name=field_name,
                kind=kind.value,
                value=value,
                extra=(
                    f"min {_TOKEN_ADDRESS_MIN_LENGTH} "
                    f"max {_TOKEN_ADDRESS_MAX_LENGTH}"
                ),
            )
        if not _BASE58_CHAR_RE.match(value):
            _raise_violation(
                code=Stage21ErrorCode.E2155,
                field_name=field_name,
                kind=kind.value,
                value=value,
            )
        # R6: TOKEN_ADDRESS rejects only URL fragments; it does
        # NOT apply the full forbidden-substring list because a
        # real base58 mint may incidentally contain the substring
        # "token" / "secret" / "credential" / etc. The URL-scheme
        # fragments come from constants.py so the literal URL
        # substrings never appear in this source file.
        lower = value.lower()
        for url_frag in _TOKEN_ADDRESS_URL_FRAGMENTS:
            if url_frag in lower:
                _raise_violation(
                    code=Stage21ErrorCode.E2153,
                    field_name=field_name,
                    kind=kind.value,
                    value=value,
                    extra=f"matched {url_frag}",
                )
    else:
        # Unreachable; SafeStringKind is exhaustive.
        raise AssertionError(f"Unknown SafeStringKind: {kind!r}")


def validate_timestamp_value(
    value: object,
    *,
    field_name: str,
) -> None:
    """Validate ``value`` as an RFC3339 UTC timestamp string.

    Fail-closed. The forbidden-substring scan still applies to
    the timestamp value (e.g. an injected URL-scheme substring in
    a fake-RFC3339-shaped string would be caught).
    """
    if not isinstance(value, str):
        _raise_violation(
            code=Stage21ErrorCode.E2158,
            field_name=field_name,
            kind="TIMESTAMP",
            value=value,
            extra=f"actual_type {type(value).__name__}",
        )
    if not _RFC3339_UTC_RE.match(value):
        _raise_violation(
            code=Stage21ErrorCode.E2152,
            field_name=field_name,
            kind="TIMESTAMP",
            value=value,
        )
    sub = _matched_forbidden_substring(value)
    if sub is not None:
        _raise_violation(
            code=Stage21ErrorCode.E2153,
            field_name=field_name,
            kind="TIMESTAMP",
            value=value,
            extra=f"matched={sub}",
        )


def validate_payload_hash_value(
    value: object,
    *,
    field_name: str,
) -> None:
    """Validate ``value`` as exactly 64 lowercase hex chars (sha256)."""
    if not isinstance(value, str):
        _raise_violation(
            code=Stage21ErrorCode.E2158,
            field_name=field_name,
            kind="PAYLOAD_HASH",
            value=value,
            extra=f"actual_type {type(value).__name__}",
        )
    if not _PAYLOAD_HASH_RE.match(value):
        _raise_violation(
            code=Stage21ErrorCode.E2152,
            field_name=field_name,
            kind="PAYLOAD_HASH",
            value=value,
        )


# ---------------------------------------------------------------------------
# Payload dict validator (R9)
# ---------------------------------------------------------------------------


def _infer_value_handler(key: str) -> str:
    """Return a label naming the handler used to validate value of ``key``.

    Returns one of:
      "TOKEN_ADDRESS"     -> SafeStringKind.TOKEN_ADDRESS
      "PAYLOAD_HASH"      -> validate_payload_hash_value
      "TIMESTAMP"         -> validate_timestamp_value
      "SHORT_IDENTIFIER"  -> SafeStringKind.SHORT_IDENTIFIER
      "SHORT_LABEL"       -> SafeStringKind.SHORT_LABEL  (default)
    """
    if key in _TOKEN_ADDRESS_KEYS:
        return "TOKEN_ADDRESS"
    if key in _HASH_KEYS:
        return "PAYLOAD_HASH"
    if key in _TIMESTAMP_KEYS:
        return "TIMESTAMP"
    if key in _SHORT_IDENTIFIER_KEYS:
        return "SHORT_IDENTIFIER"
    return "SHORT_LABEL"


def validate_safe_payload_dict(
    payload: Any,
    *,
    field_name: str = "payload",
    exempt_keys: frozenset[str] = MARKER_EXEMPT_KEYS_DEFAULT,
) -> None:
    """Recursively validate ``payload`` per Stage 21.2 R9.

    Behavior:
      * The root must be a ``Mapping``; otherwise E2158.
      * Nesting depth > _PAYLOAD_MAX_DEPTH raises E2156.
      * Total node count > _PAYLOAD_MAX_NODES raises E2157.
      * Every key must be a ``str``. Keys are validated as
        SHORT_LABEL except for known-safe domain keys
        (``token_address`` / ``token_mint``) which are accepted
        verbatim.
      * The bare key name ``"token"`` is forbidden everywhere
        (R5); raises E2153 ``matched=bare-token-key-forbidden``.
      * Values are routed by key-name to one of: TOKEN_ADDRESS,
        PAYLOAD_HASH, TIMESTAMP, SHORT_IDENTIFIER, or SHORT_LABEL
        (default).
      * Keys in ``exempt_keys`` (caller-supplied) and in
        ``RENDERED_TEXT_EXEMPT_KEYS`` (built-in) bypass value
        predicate validation; their values are still counted in
        the node budget.
      * ``None``, ``bool``, ``int``, ``float`` leaf values pass
        without further check. Any other leaf value type raises
        E2158.

    Fail-closed. Raises ``Stage21Error`` on any violation.
    """
    if not isinstance(payload, Mapping):
        _raise_violation(
            code=Stage21ErrorCode.E2158,
            field_name=field_name,
            kind="PAYLOAD",
            value=payload,
            extra=f"actual_type={type(payload).__name__}",
        )

    nodes_seen = [0]

    def _check_node_budget(path: str) -> None:
        if nodes_seen[0] > _PAYLOAD_MAX_NODES:
            _raise_violation(
                code=Stage21ErrorCode.E2157,
                field_name=path,
                kind="PAYLOAD",
                value=str(nodes_seen[0]),
                extra=f"max {_PAYLOAD_MAX_NODES}",
            )

    def _validate_leaf(
        key: Optional[str],
        value: Any,
        path: str,
    ) -> None:
        nodes_seen[0] += 1
        _check_node_budget(path)
        if value is None:
            return
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            return
        if isinstance(value, str):
            if key is None:
                validate_safe_string(
                    value,
                    kind=SafeStringKind.SHORT_LABEL,
                    field_name=path,
                )
                return
            handler = _infer_value_handler(key)
            if handler == "TIMESTAMP":
                validate_timestamp_value(value, field_name=path)
            elif handler == "PAYLOAD_HASH":
                validate_payload_hash_value(value, field_name=path)
            elif handler == "TOKEN_ADDRESS":
                validate_safe_string(
                    value,
                    kind=SafeStringKind.TOKEN_ADDRESS,
                    field_name=path,
                )
            elif handler == "SHORT_IDENTIFIER":
                validate_safe_string(
                    value,
                    kind=SafeStringKind.SHORT_IDENTIFIER,
                    field_name=path,
                )
            else:
                validate_safe_string(
                    value,
                    kind=SafeStringKind.SHORT_LABEL,
                    field_name=path,
                )
            return
        _raise_violation(
            code=Stage21ErrorCode.E2158,
            field_name=path,
            kind="PAYLOAD_VALUE",
            value=value,
            extra=f"actual_type {type(value).__name__}",
        )

    def _walk(node: Any, depth: int, path: str) -> None:
        if depth > _PAYLOAD_MAX_DEPTH:
            _raise_violation(
                code=Stage21ErrorCode.E2156,
                field_name=path,
                kind="PAYLOAD",
                value=str(depth),
                extra=f"max {_PAYLOAD_MAX_DEPTH}",
            )
        nodes_seen[0] += 1
        _check_node_budget(path)
        if isinstance(node, Mapping):
            for k, v in node.items():
                if not isinstance(k, str):
                    _raise_violation(
                        code=Stage21ErrorCode.E2158,
                        field_name=path,
                        kind="PAYLOAD_KEY",
                        value=k,
                        extra=f"key_type {type(k).__name__}",
                    )
                # Bare "token" key is universally forbidden (R5).
                if k == "token":
                    _raise_violation(
                        code=Stage21ErrorCode.E2153,
                        field_name=f"{path}.{k}",
                        kind="PAYLOAD_KEY",
                        value=k,
                        extra="matched bare-token-key-forbidden",
                    )
                # Validate the key as SHORT_LABEL unless it is a
                # known-safe domain key (token_address / token_mint).
                if k not in _SAFE_DOMAIN_TOKEN_KEYS_SET:
                    validate_safe_string(
                        k,
                        kind=SafeStringKind.SHORT_LABEL,
                        field_name=f"{path}.{k}.key",
                    )
                child_path = f"{path}.{k}"
                if k in exempt_keys or k in RENDERED_TEXT_EXEMPT_KEYS:
                    # Marker-exempt or rendered-text-exempt: skip
                    # predicate validation but still count the
                    # value as a node in the budget.
                    nodes_seen[0] += 1
                    _check_node_budget(child_path)
                    continue
                if isinstance(v, (Mapping, list, tuple)):
                    _walk(v, depth + 1, child_path)
                else:
                    _validate_leaf(k, v, child_path)
        elif isinstance(node, (list, tuple)):
            for i, item in enumerate(node):
                child_path = f"{path}[{i}]"
                if isinstance(item, (Mapping, list, tuple)):
                    _walk(item, depth + 1, child_path)
                else:
                    _validate_leaf(None, item, child_path)
        else:
            # Unreachable: _walk is only called on Mappings and on
            # lists/tuples; leaf scalars go through _validate_leaf.
            _validate_leaf(None, node, path)

    _walk(payload, 0, field_name)


__all__ = [
    "FORBIDDEN_SUBSTRINGS",
    "MARKER_EXEMPT_KEYS_DEFAULT",
    "RENDERED_TEXT_EXEMPT_KEYS",
    "SafeStringKind",
    "validate_payload_hash_value",
    "validate_safe_payload_dict",
    "validate_safe_string",
    "validate_timestamp_value",
]
