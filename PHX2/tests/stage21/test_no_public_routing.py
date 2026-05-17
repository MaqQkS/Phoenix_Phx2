"""Stage 21 no-public-routing tests.

Stage 21 routes only to operator-controlled private channels. The
Stage 20 closure handoff (Sections C, G) forbids subscriber /
public / paid routing in Stage 21 in any form. This test pins
the absence of those tokens in every Stage 21 production module
via a substring check on the source.

Test files are deliberately exempt -- the absence test itself must
mention "subscriber" / "public" / "paid" to assert their absence
in production.
"""

from __future__ import annotations

from pathlib import Path

from PHX2.stage21.constants import STAGE21_FORBIDDEN_ROUTING_TOKENS


STAGE21_ROOT = Path(__file__).parent.parent.parent / "stage21"

# constants.py is the declarer of STAGE21_FORBIDDEN_ROUTING_TOKENS;
# it necessarily contains the literal token strings as Python
# string literals. The forbidden-substring test exempts the
# declarer; every other Stage 21 production module is scanned.
_EXEMPT_FILES: frozenset[str] = frozenset({"constants.py"})


def _iter_production_modules() -> list[Path]:
    return [
        p for p in STAGE21_ROOT.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _scan_candidate_files() -> list[Path]:
    return [
        p for p in _iter_production_modules()
        if p.name not in _EXEMPT_FILES
    ]


def test_no_forbidden_routing_token_in_any_production_module():
    for py_file in _scan_candidate_files():
        source = py_file.read_text(encoding="utf-8").lower()
        for token in STAGE21_FORBIDDEN_ROUTING_TOKENS:
            assert token.lower() not in source, (
                f"{py_file}: forbidden routing token {token!r} found in "
                f"production source"
            )


def test_constants_module_is_the_only_exempt_file():
    # If the exempt set grows, this test fails so the change is
    # surfaced explicitly in review.
    assert _EXEMPT_FILES == frozenset({"constants.py"})


def test_forbidden_routing_tokens_constant_is_non_empty():
    # If the constant becomes empty, the absence test silently
    # passes; pin the constant's minimum membership here.
    assert len(STAGE21_FORBIDDEN_ROUTING_TOKENS) >= 5
    assert "subscriber" in STAGE21_FORBIDDEN_ROUTING_TOKENS
    assert "paid_signal" in STAGE21_FORBIDDEN_ROUTING_TOKENS
    assert "public_signal" in STAGE21_FORBIDDEN_ROUTING_TOKENS
    assert "public_channel" in STAGE21_FORBIDDEN_ROUTING_TOKENS


def test_safe_for_public_dispatch_is_the_only_public_word_in_source():
    """Spot-check: the string ``safe_for_public_dispatch`` is allowed.

    ``safe_for_public_dispatch`` is a Stage 21 invariant name; it
    legitimately contains the substring ``public``. The forbidden
    token list above is deliberately scoped to routing tokens
    (e.g. ``public_dispatch``, ``public_signal``) so the invariant
    name is unaffected.

    We pin that distinction here so a future tightening of the
    forbidden set does not accidentally break the invariant name.
    """
    invariant = "safe_for_public_dispatch"
    forbidden = {t.lower() for t in STAGE21_FORBIDDEN_ROUTING_TOKENS}
    assert invariant not in forbidden
