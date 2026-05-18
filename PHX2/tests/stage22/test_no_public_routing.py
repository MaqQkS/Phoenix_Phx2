"""Stage 22 no-public-routing tests.

Stage 22 inherits the Stage 21 invariant: subscriber / public /
paid routing is forbidden anywhere in this stage. The Stage 22
forbidden-token tuple lives in
``PHX2/stage22/constants.STAGE22_FORBIDDEN_ROUTING_TOKENS`` and
mirrors Stage 21's set exactly.

The scanner walks the AST of every Stage 22 production module
and extracts identifiers from identifier positions only (Name /
Attribute / FunctionDef / ClassDef / arg / keyword /
import-alias). String literals are NOT identifiers and are not
scanned, so ``PHX2/stage22/constants.py`` -- which declares the
forbidden tuple as a sequence of string literals -- does not
need a file-level exemption.

For each extracted identifier the scanner asks:

  * Is the identifier in the explicit-allowed set
    (``STAGE22_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS``)? If yes,
    allow.
  * Does the identifier exactly equal a forbidden token, or
    contain a forbidden token as a snake-component
    (``T_...`` / ``..._T`` / ``..._T_...``)? If yes, fail.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage22.constants import (
    STAGE22_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS,
    STAGE22_FORBIDDEN_ROUTING_TOKENS,
)


STAGE22_ROOT = Path(__file__).parent.parent.parent / "stage22"


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE22_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _extract_identifiers(source: str) -> set[str]:
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            idents.add(node.name)
            if node.asname:
                idents.add(node.asname)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for component in mod.split("."):
                if component:
                    idents.add(component)
    return idents


def _identifier_violates_routing_tokens(ident: str) -> str | None:
    """Return the forbidden token that ``ident`` matches, or ``None``.

    Match rules:

      * The identifier exactly equals a forbidden token, or
      * The identifier contains a forbidden token as a
        snake-component: the token appears as a prefix, suffix,
        or middle component bounded by ``_`` on at least one side.

    Identifiers in
    ``STAGE22_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS`` are exempt.
    """
    if ident in STAGE22_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS:
        return None
    lower = ident.lower()
    for token in STAGE22_FORBIDDEN_ROUTING_TOKENS:
        if lower == token:
            return token
        # snake-bounded: prefix, suffix, or middle.
        if (
            lower.startswith(token + "_")
            or lower.endswith("_" + token)
            or ("_" + token + "_") in lower
        ):
            return token
    return None


# ---------------------------------------------------------------------------
# Production tree scan
# ---------------------------------------------------------------------------


def test_every_stage22_production_identifier_is_routing_clean():
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        for ident in _extract_identifiers(source):
            matched = _identifier_violates_routing_tokens(ident)
            assert matched is None, (
                f"{py_file}: identifier {ident!r} matches forbidden "
                f"routing token {matched!r}"
            )


# ---------------------------------------------------------------------------
# Source-text scan: forbidden tokens must not appear as bare substrings
# in production source either, regardless of identifier shape.
# ---------------------------------------------------------------------------


def test_forbidden_routing_tokens_only_appear_in_locked_constants_tuple():
    """The locked forbidden-token strings appear ONLY in
    ``constants.py`` (where they are declared as the tuple value)
    and ``__init__.py`` / module docstrings (where they may be
    mentioned in documentation prose).

    Every other production file must contain none of the
    forbidden tokens at the source-text level.
    """
    allowed_files = {
        STAGE22_ROOT / "constants.py",
        STAGE22_ROOT / "__init__.py",
    }
    for py_file in _iter_production_modules():
        if py_file in allowed_files:
            continue
        source = py_file.read_text(encoding="utf-8")
        for token in STAGE22_FORBIDDEN_ROUTING_TOKENS:
            assert token not in source, (
                f"{py_file}: forbidden routing token {token!r} appears "
                "in source outside the locked constants declaration"
            )


# ---------------------------------------------------------------------------
# Negative fixtures
# ---------------------------------------------------------------------------


def test_scanner_detects_exact_match_identifier():
    assert _identifier_violates_routing_tokens("subscriber") == "subscriber"


def test_scanner_detects_snake_prefix():
    assert (
        _identifier_violates_routing_tokens("subscriber_router")
        == "subscriber"
    )


def test_scanner_detects_snake_suffix():
    assert (
        _identifier_violates_routing_tokens("dispatch_public_dispatch")
        == "public_dispatch"
    )


def test_scanner_detects_snake_middle():
    assert (
        _identifier_violates_routing_tokens("a_paid_dispatch_b")
        == "paid_dispatch"
    )


def test_scanner_allows_safe_for_public_dispatch():
    assert (
        _identifier_violates_routing_tokens("safe_for_public_dispatch")
        is None
    )


def test_scanner_allows_uppercase_safe_for_public_dispatch():
    assert (
        _identifier_violates_routing_tokens("SAFE_FOR_PUBLIC_DISPATCH")
        is None
    )


def test_scanner_allows_unrelated_identifier():
    assert _identifier_violates_routing_tokens("provider_id") is None


def test_scanner_does_not_false_positive_on_subscribers_substring_word():
    """The token ``subscribers`` is in the forbidden set; an
    identifier like ``subscribers`` matches but a hypothetical
    unrelated word like ``transcribers`` (which contains
    ``scribers`` as a substring but does NOT contain
    ``subscribers`` as a snake-component) should pass.

    The scanner only matches snake-bounded forms; pure substring
    matches without snake delimiters are not flagged.
    """
    # ``transcribers`` does not contain "subscribers" as a
    # snake-bounded component.
    assert (
        _identifier_violates_routing_tokens("transcribers")
        is None
    )
