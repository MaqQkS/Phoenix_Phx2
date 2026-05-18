"""Stage 22.1 secret-leak boundary tests.

Per the Stage 22.1 design-lock §11 correction §2:

  * Stage 22.1 records are plain ``NamedTuple`` shapes that
    accept caller-supplied strings. Plain ``NamedTuple.repr``
    echoes field values by design; we DO NOT assert that repr
    sanitizes arbitrary attacker-supplied field content. That
    redaction belongs to a later capture/writer implementation.
  * Stage 22.1's leak invariants instead live at the source-text
    level and at the field-name level.

This file enforces:

  * No production source contains a URL literal
    (``https://`` / ``http://`` / ``wss://`` / ``ws://``).
  * No production source contains a known webhook hostname
    (``discord.com`` / ``discordapp.com`` / ``hooks.slack.com``).
  * No production source contains a Phoenix1 sqlite filename
    (``bot.db``).
  * No production source declares a secret-bearing field name
    on any NamedTuple (no ``api_key`` / ``webhook_url`` /
    ``rpc_url`` / ``raw_response_body`` / ``exception_message``
    / ``exception_repr`` / ``headers`` / ``authorization`` /
    ``bearer`` / ``password`` / ``secret`` / ``credential``).
  * No production source contains a string literal that
    matches a long-token leak shape (URL fragment, long hex
    run, long base64 run) -- defense-in-depth against
    accidentally-pasted credentials.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


STAGE22_ROOT = Path(__file__).parent.parent.parent / "stage22"


_FORBIDDEN_SOURCE_SUBSTRINGS: tuple[str, ...] = (
    "https://",
    "http://",
    "wss://",
    "ws://",
    "discord.com",
    "discordapp.com",
    "hooks.slack.com",
    "bot.db",
)


_FORBIDDEN_FIELD_NAME_SUBSTRINGS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "webhook_url",
    "webhook",
    "rpc_url",
    "raw_response_body",
    "raw_response",
    "response_body",
    "exception_message",
    "exception_repr",
    "exception_args",
    "headers",
    "authorization",
    "bearer",
    "password",
    "secret",
    "credential",
    "credentials",
    "private_key",
    "privatekey",
)


# Long-token shapes considered leak candidates. The thresholds
# are intentionally above the Stage 21 SHA-256 fingerprint length
# (12 hex chars) so the truncated fingerprints used elsewhere do
# not trip this scan. Hash-derivation field names in 22.1
# (raw_event_hash) take precomputed strings from the caller; no
# literal hash appears in 22.1 source.
_LONG_HEX_RE = re.compile(r"[a-fA-F0-9]{40,}")
# URL-safe base64 (alphanumeric + ``+`` / ``=`` / ``-`` / ``_``)
# of length >= 32. ``/`` is intentionally excluded because it is
# a path separator that appears in benign file-path docstrings
# (e.g. ``PHX2/stage22/failure_classification``); URL prefixes
# are caught separately by ``_FORBIDDEN_SOURCE_SUBSTRINGS``.
# Modern API token formats (Discord, Helius, AWS access keys,
# JWT) use the URL-safe alphabet without ``/``, so excluding it
# does not lose coverage for the realistic leak shapes.
_LONG_BASE64ISH_RE = re.compile(r"[A-Za-z0-9+=_-]{32,}")


# Identifier patterns considered safe even if long enough to
# match _LONG_BASE64ISH_RE. The Stage 22 closed-set token names
# and the locked vocabulary are all short, but several identifier
# names span 32+ chars; the test treats those identifier names
# as safe and only flags non-identifier shapes.
_SCREAMING_SNAKE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SNAKE_LOWER_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_PASCAL_CASE_RE = re.compile(r"^[A-Z][a-z][A-Za-z0-9]*$")
_PRIVATE_NAME_RE = re.compile(r"^_[a-zA-Z0-9_]*$")
_HYPHENATED_LOWER_RE = re.compile(r"^[a-z]+(-[a-z]+)+$")


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE22_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _is_safe_identifier_shape(s: str) -> bool:
    return bool(
        _SCREAMING_SNAKE_RE.fullmatch(s)
        or _SNAKE_LOWER_RE.fullmatch(s)
        or _PASCAL_CASE_RE.fullmatch(s)
        or _PRIVATE_NAME_RE.fullmatch(s)
        or _HYPHENATED_LOWER_RE.fullmatch(s)
    )


# ---------------------------------------------------------------------------
# Source-level substring scans
# ---------------------------------------------------------------------------


def test_no_forbidden_substring_in_production_source():
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_SOURCE_SUBSTRINGS:
            assert needle not in source, (
                f"{py_file}: forbidden substring {needle!r} in source"
            )


# ---------------------------------------------------------------------------
# Field-name discipline on every NamedTuple declared in Stage 22.1
# ---------------------------------------------------------------------------


def _collect_namedtuple_field_names(source: str) -> list[tuple[str, str]]:
    """Return ``[(class_name, field_name), ...]`` for every class
    declared in ``source`` whose body declares typed fields via
    ``AnnAssign`` (the standard ``NamedTuple`` class-syntax style).

    The function does not require the class to actually subclass
    ``NamedTuple`` -- it conservatively reports every typed
    class-level attribute so the forbidden-field-name scan also
    catches typed fields on a future ``dataclass`` or any other
    class-shape we may grow.
    """
    tree = ast.parse(source)
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(
                    item.target, ast.Name
                ):
                    out.append((node.name, item.target.id))
    return out


def test_no_namedtuple_field_has_secret_bearing_name():
    for py_file in _iter_production_modules():
        for class_name, field_name in _collect_namedtuple_field_names(
            py_file.read_text(encoding="utf-8")
        ):
            lower = field_name.lower()
            for forbidden in _FORBIDDEN_FIELD_NAME_SUBSTRINGS:
                assert forbidden not in lower, (
                    f"{py_file}: class {class_name!r} has forbidden "
                    f"secret-bearing field name {field_name!r} "
                    f"(matched substring {forbidden!r})"
                )


# ---------------------------------------------------------------------------
# Classifier output discipline: closed-set strings only
# ---------------------------------------------------------------------------


def test_classifier_output_never_includes_raw_exception_material():
    """Drives ``classify_failure`` through several adversarial-shape
    inputs and asserts the returned label is always one of the
    closed-set ``PROVIDER_FAILURE_LABELS`` tokens.

    This is the runtime complement to the field-name discipline:
    even if a caller passes a URL-shaped string as
    ``upstream_error_type``, the classifier raises rather than
    echoing it.
    """
    from PHX2.stage22.constants import (
        PROVIDER_FAILURE_LABELS,
        STATUS_CLASS_CONNECTION,
        STATUS_CLASS_SERVER_ERROR,
        STATUS_CLASS_TIMEOUT,
        UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED,
        UPSTREAM_ERROR_TYPE_SERVER_ERROR,
        UPSTREAM_ERROR_TYPE_TIMEOUT,
    )
    from PHX2.stage22.errors import Stage22ClassifierContractError
    from PHX2.stage22.failure_classification import classify_failure
    from PHX2.stage22.ingest_contracts import ProviderFetchOutcome

    label_set = set(PROVIDER_FAILURE_LABELS)
    good_inputs = (
        (STATUS_CLASS_TIMEOUT, UPSTREAM_ERROR_TYPE_TIMEOUT),
        (STATUS_CLASS_SERVER_ERROR, UPSTREAM_ERROR_TYPE_SERVER_ERROR),
        (STATUS_CLASS_CONNECTION, UPSTREAM_ERROR_TYPE_CONNECTION_REFUSED),
    )
    for status_class, upstream_error_type in good_inputs:
        out = ProviderFetchOutcome(
            ok=False,
            responses=(),
            status_class=status_class,
            upstream_error_type=upstream_error_type,
            provider_attempt_index=0,
        )
        label = classify_failure(outcome=out)
        assert label in label_set, (
            f"classify_failure produced non-locked label {label!r}"
        )

    # Adversarial: caller passes a URL-shaped upstream_error_type
    # (which is OUTSIDE the closed UPSTREAM_ERROR_TYPES set).
    # The classifier MUST raise rather than echo.
    adversarial = ProviderFetchOutcome(
        ok=False,
        responses=(),
        status_class=STATUS_CLASS_TIMEOUT,
        upstream_error_type=(
            "h" + "ttps://attacker.invalid/SECRET_TOKEN_AbCdEf"
        ),
        provider_attempt_index=0,
    )
    import pytest as _pytest

    with _pytest.raises(Stage22ClassifierContractError):
        classify_failure(outcome=adversarial)


# ---------------------------------------------------------------------------
# Long-token leak shapes in production source
# ---------------------------------------------------------------------------


def test_no_long_hex_run_in_production_source():
    """Catches accidentally-pasted long hex tokens (>= 40 chars).

    Stage 22.1 does not need any literal hex string of that
    length. ``raw_event_hash`` values are caller-supplied at
    runtime and never appear as source literals.
    """
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        match = _LONG_HEX_RE.search(source)
        assert match is None, (
            f"{py_file}: forbidden long hex run at offset {match.start()}: "
            f"{match.group(0)[:16]!r}..."
        )


def _looks_like_a_token_payload(s: str) -> bool:
    """Return True iff ``s`` has the mixed-content shape of a
    secret token: at least one ASCII letter AND at least one
    digit, with the total alphanumeric content covering most of
    the string. Pure-punctuation runs (docstring dividers like
    ``-----------``) and pure-letter runs are not token shapes.
    """
    has_letter = any(c.isalpha() for c in s)
    has_digit = any(c.isdigit() for c in s)
    alphanumeric = sum(1 for c in s if c.isalnum())
    if not (has_letter and has_digit):
        return False
    # Real tokens are >= 80% alphanumeric. Docstring dividers,
    # syntax fragments, and ASCII art typically fall under this
    # threshold.
    return alphanumeric / len(s) >= 0.8


def test_no_unsafe_long_base64ish_run_in_production_source():
    """Catches accidentally-pasted long base64-shaped tokens.

    The scan accepts long identifier-shaped tokens (Stage 22
    constant names) and pure-punctuation runs (docstring
    dividers). Only strings with the mixed-content shape of a
    realistic secret token are flagged.
    """
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        for match in _LONG_BASE64ISH_RE.finditer(source):
            token = match.group(0)
            if _is_safe_identifier_shape(token):
                continue
            if not _looks_like_a_token_payload(token):
                continue
            raise AssertionError(
                f"{py_file}: suspicious long token at offset "
                f"{match.start()}: {token[:24]!r}..."
            )


# ---------------------------------------------------------------------------
# Cross-stage discipline: Stage 22 production must not echo Stage 21
# env-var names verbatim into source either, since those name strings
# are sensitive context labels.
# ---------------------------------------------------------------------------


def test_no_stage21_secret_env_var_name_appears_in_stage22_source():
    """Stage 22.1 does not read env vars; it must not even mention
    the Stage 21 secret env-var name strings.

    The Stage 21 ``STAGE21_SECRET_ENV_VARS`` tuple lists every
    secret-bearing env-var name. Stage 22.1 production source
    should never need any of these literal strings.
    """
    from PHX2.stage21.constants import STAGE21_SECRET_ENV_VARS

    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        for name in STAGE21_SECRET_ENV_VARS:
            assert name not in source, (
                f"{py_file}: forbidden Stage 21 secret env-var name "
                f"{name!r} appears in source"
            )
