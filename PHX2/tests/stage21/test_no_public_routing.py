"""Stage 21 no-public-routing tests.

Stage 21 routes only to operator-controlled private channels. The
Stage 20 closure handoff (Sections C, G) forbids subscriber /
public / paid routing in Stage 21 in any form.

AUDIT-004: the scanner is now identifier-aware. It walks the AST
of every Stage 21 production module and extracts identifiers from
identifier positions only (Name / Attribute / FunctionDef /
ClassDef / arg / keyword / import-alias). String literals are NOT
identifiers and are not scanned for forbidden tokens; that is why
``PHX2/stage21/constants.py`` -- which declares the forbidden
tuple as a sequence of string literals -- no longer needs a
file-level exemption.

For each extracted identifier the scanner asks:
  * Is this identifier in the explicit-allowed set
    (``STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS``)? If yes,
    allow.
  * Does the identifier exactly equal a forbidden token, or
    contain a forbidden token as a snake-component (``T_...`` /
    ``..._T`` / ``..._T_...``)? If yes, fail.

This catches ``public_dispatch`` and ``paid_dispatch`` (which the
prior substring scanner had to exclude due to false positives on
``safe_for_public_dispatch``).
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage21.constants import (
    STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS,
    STAGE21_FORBIDDEN_ROUTING_TOKENS,
)


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE21_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _extract_identifiers(source: str) -> set[str]:
    """Return every identifier-position name in ``source``.

    Sources of identifiers:
      * ``ast.Name``                  (Load / Store / Del contexts)
      * ``ast.Attribute``             (``.attr`` only)
      * ``ast.FunctionDef``           (``name``)
      * ``ast.AsyncFunctionDef``      (``name``)
      * ``ast.ClassDef``              (``name``)
      * ``ast.arg``                   (``arg``)
      * ``ast.keyword``               (``arg`` if non-None)
      * ``ast.alias``                 (``name`` / ``asname``)
      * ``ast.ImportFrom``            (module path components)

    Dotted import paths like ``"PHX2.stage21.constants"`` are
    split on ``.`` so each component contributes individually.
    """
    tree = ast.parse(source)
    idents: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            idents.add(node.id)
        elif isinstance(node, ast.Attribute):
            idents.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            idents.add(node.name)
        elif isinstance(node, ast.arg):
            idents.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            idents.add(node.arg)
        elif isinstance(node, ast.alias):
            for part in node.name.split("."):
                if part:
                    idents.add(part)
            if node.asname:
                idents.add(node.asname)
        elif isinstance(node, ast.ImportFrom) and node.module:
            for part in node.module.split("."):
                if part:
                    idents.add(part)
    return idents


_FORBIDDEN_LOWER: tuple[str, ...] = tuple(
    t.lower() for t in STAGE21_FORBIDDEN_ROUTING_TOKENS
)
_EXPLICIT_ALLOWED_LOWER: frozenset[str] = frozenset(
    i.lower() for i in STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS
)


def _identifier_violates(ident: str) -> str:
    """Return the matched forbidden token, or "" if the identifier is clean.

    Whitelist check is performed first. After that, an identifier
    violates if:
      * it is exactly a forbidden token, OR
      * it contains a forbidden token as a snake-component
        (start ``T_``, end ``_T``, or middle ``_T_``).

    The check is case-insensitive (lowercased compare).
    """
    lower = ident.lower()
    if lower in _EXPLICIT_ALLOWED_LOWER:
        return ""
    for token in _FORBIDDEN_LOWER:
        if lower == token:
            return token
        # As a snake-cased component.
        if (
            lower.startswith(token + "_")
            or lower.endswith("_" + token)
            or ("_" + token + "_") in lower
        ):
            return token
    return ""


# ---------------------------------------------------------------------------
# Production-tree checks
# ---------------------------------------------------------------------------


def test_no_forbidden_routing_identifier_in_any_production_module():
    for py_file in _iter_production_modules():
        source = py_file.read_text(encoding="utf-8")
        for ident in _extract_identifiers(source):
            matched = _identifier_violates(ident)
            assert matched == "", (
                f"{py_file}: identifier {ident!r} carries forbidden "
                f"routing token {matched!r}"
            )


def test_safe_for_public_dispatch_identifier_is_allowed_by_whitelist():
    # Verify the locked invariant identifier is on the whitelist
    # and does NOT trip the forbidden check.
    assert _identifier_violates("safe_for_public_dispatch") == ""
    assert _identifier_violates("SAFE_FOR_PUBLIC_DISPATCH") == ""


def test_real_public_dispatch_identifier_is_caught():
    # The exact forbidden token as a bare identifier is caught.
    assert _identifier_violates("public_dispatch") == "public_dispatch"


def test_real_paid_dispatch_identifier_is_caught():
    assert _identifier_violates("paid_dispatch") == "paid_dispatch"


def test_compound_forbidden_identifier_is_caught_via_components():
    # Component-aware match catches forms like
    # ``send_to_public_dispatch`` or ``subscriber_route_outbound``.
    assert _identifier_violates("send_to_public_dispatch") == "public_dispatch"
    assert _identifier_violates("subscriber_route") == "subscriber"
    assert _identifier_violates("queue_paid_signal_sink") == "paid_signal"


def test_unrelated_identifier_with_substring_collision_is_safe():
    # The substring "public" appears in many legitimate names; only
    # full forbidden tokens trip the check.
    assert _identifier_violates("publication_count") == ""
    assert _identifier_violates("publisher_name") == ""


# ---------------------------------------------------------------------------
# Negative fixtures: prove the AST identifier extractor catches
# real-code occurrences and ignores docstring / string-literal
# mentions.
# ---------------------------------------------------------------------------


def _module_has_violation(source: str) -> bool:
    return any(
        _identifier_violates(ident)
        for ident in _extract_identifiers(source)
    )


def test_extractor_flags_public_dispatch_as_variable_name():
    source = "public_dispatch = True\n"
    assert _module_has_violation(source)


def test_extractor_flags_paid_dispatch_as_function_name():
    source = "def paid_dispatch():\n    return None\n"
    assert _module_has_violation(source)


def test_extractor_flags_subscriber_as_attribute_access():
    source = "obj.subscriber = 1\n"
    assert _module_has_violation(source)


def test_extractor_flags_public_signal_as_class_name():
    source = "class public_signal:\n    pass\n"
    assert _module_has_violation(source)


def test_extractor_flags_import_alias():
    # ``import x as public_dispatch`` -- the binding name is the
    # forbidden token.
    source = "import os as public_dispatch\n"
    assert _module_has_violation(source)


def test_extractor_flags_kwarg_name():
    source = "f(public_dispatch=True)\n"
    assert _module_has_violation(source)


def test_extractor_ignores_string_literal_mentions():
    # Constants module relies on this: a string literal value of
    # "subscriber" is not an identifier and must not be flagged.
    source = (
        "FORBIDDEN = ('subscriber', 'public_dispatch', 'paid_dispatch')\n"
    )
    assert not _module_has_violation(source)


def test_extractor_ignores_docstring_mentions():
    source = '"""This docstring mentions public_dispatch but uses no such symbol."""\n'
    assert not _module_has_violation(source)


def test_extractor_ignores_comment_mentions():
    source = "# public_dispatch is forbidden\nX = 1\n"
    assert not _module_has_violation(source)


def test_extractor_allows_safe_for_public_dispatch_field():
    source = (
        "class Marker:\n"
        "    safe_for_public_dispatch: bool = False\n"
    )
    assert not _module_has_violation(source)


def test_forbidden_routing_tokens_constant_minimum_membership():
    # If a future change removes a forbidden token, this test
    # fails so the change is surfaced explicitly in review.
    declared = set(STAGE21_FORBIDDEN_ROUTING_TOKENS)
    required = {
        "subscriber",
        "subscribers",
        "subscriber_channel",
        "public_channel",
        "public_signal",
        "public_dispatch",
        "paid_signal",
        "paid_signals",
        "paid_channel",
        "paid_dispatch",
    }
    missing = required - declared
    assert not missing, f"missing required forbidden tokens: {missing}"


def test_explicit_allowed_identifier_set_is_locked():
    # The whitelist must remain narrow: only the locked invariant
    # name in two casings. Adding to it is an explicit operator
    # decision.
    assert frozenset(STAGE21_EXPLICIT_ROUTING_ALLOWED_IDENTIFIERS) == frozenset({
        "safe_for_public_dispatch",
        "SAFE_FOR_PUBLIC_DISPATCH",
    })
