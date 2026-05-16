"""Stage 20.2 forbidden-artifact absence (Phase D).

Three grep-style checks, each implemented via Python file walks
so the test source itself does NOT contain the literal forbidden
tokens. The tokens are reconstructed at runtime so a final
``grep -rn`` pass against ``PHX2/`` and ``PHX2/(tests/)?stage20/``
returns zero matches.

Also includes the AST-based mapping-reuse guard from Phase D
constraint F: no module under ``PHX2/stage20/`` or
``PHX2/tests/stage20/`` may bind ``LABEL_TO_STATE_MAPPING_V0``
except ``PHX2/stage20/constants.py`` (the legitimate definition).
"""

from __future__ import annotations

import ast
import pathlib


# ---------------------------------------------------------------------------
# Runtime-only token reconstruction
# ---------------------------------------------------------------------------


def _forbidden_extra_e_code() -> str:
    """Reconstruct the forbidden extra E-code without embedding it.

    Built from the prefix "E" plus the literal four-digit integer.
    A contiguous source-byte instance of the assembled token never
    appears in this file.
    """

    return "E" + str(2026)


def _forbidden_fim_token() -> str:
    """Reconstruct the forbidden filter-manifest token without
    embedding it.

    Built by concatenating three short fragments: ``"filter_"``,
    ``"interface_"``, ``"manifest"``. No contiguous source-byte
    instance of the assembled token appears anywhere in this file.
    """

    return "filter_" + "interface_" + "manifest"


# ---------------------------------------------------------------------------
# File-walking helpers
# ---------------------------------------------------------------------------


def _scan_for_token(roots: list[pathlib.Path], token: str) -> list[tuple[str, int, str]]:
    """Return every (file, lineno, line) where ``token`` appears
    as a substring across all readable files under ``roots``.
    """

    hits: list[tuple[str, int, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if not f.is_file():
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_no, line in enumerate(text.splitlines(), 1):
                if token in line:
                    hits.append((str(f), line_no, line))
    return hits


# ---------------------------------------------------------------------------
# Forbidden-token absence
# ---------------------------------------------------------------------------


def test_forbidden_extra_e_code_absent_anywhere_under_phx2():
    """Phase D constraint E:
    grep -rn "<extra-E-code>" PHX2/  ->  0 matches.
    """

    roots = [pathlib.Path("PHX2/")]
    token = _forbidden_extra_e_code()
    hits = _scan_for_token(roots, token)
    assert hits == [], (
        f"Forbidden token {token!r} found:\n"
        + "\n".join(f"  {f}:{ln}: {line}" for f, ln, line in hits)
    )


def test_forbidden_fim_absent_under_stage20_production():
    """Phase D constraint E:
    grep -rn "<filter-manifest-token>" PHX2/stage20/  ->  0 matches.
    """

    roots = [pathlib.Path("PHX2/stage20")]
    token = _forbidden_fim_token()
    hits = _scan_for_token(roots, token)
    assert hits == [], (
        f"Forbidden token {token!r} found:\n"
        + "\n".join(f"  {f}:{ln}: {line}" for f, ln, line in hits)
    )


def test_forbidden_fim_absent_under_stage20_tests():
    """Phase D constraint E:
    grep -rn "<filter-manifest-token>" PHX2/tests/stage20/  ->  0 matches.
    """

    roots = [pathlib.Path("PHX2/tests/stage20")]
    token = _forbidden_fim_token()
    hits = _scan_for_token(roots, token)
    assert hits == [], (
        f"Forbidden token {token!r} found:\n"
        + "\n".join(f"  {f}:{ln}: {line}" for f, ln, line in hits)
    )


# ---------------------------------------------------------------------------
# Mapping-reuse guard (AST-based; Phase D constraint F)
# ---------------------------------------------------------------------------

_MAPPING_NAME: str = "LABEL_TO_STATE_MAPPING_V0"
_LEGITIMATE_DEFINITION_SITE = pathlib.Path(
    "PHX2/stage20/constants.py"
).resolve()


def _find_mapping_rebinds() -> list[tuple[str, int]]:
    """Return every (file, lineno) where ``LABEL_TO_STATE_MAPPING_V0``
    is the target of an ``Assign`` or ``AnnAssign``.

    The legitimate definition in ``PHX2/stage20/constants.py`` is
    excluded.
    """

    hits: list[tuple[str, int]] = []
    roots = [
        pathlib.Path("PHX2/stage20"),
        pathlib.Path("PHX2/tests/stage20"),
    ]
    for root in roots:
        for f in sorted(root.rglob("*.py")):
            if f.resolve() == _LEGITIMATE_DEFINITION_SITE:
                continue
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if (
                            isinstance(target, ast.Name)
                            and target.id == _MAPPING_NAME
                        ):
                            hits.append((str(f), node.lineno))
                elif isinstance(node, ast.AnnAssign):
                    t = node.target
                    if (
                        isinstance(t, ast.Name)
                        and t.id == _MAPPING_NAME
                    ):
                        hits.append((str(f), node.lineno))
    return hits


def test_label_mapping_v0_not_rebound_outside_constants():
    """Phase D constraint F: only PHX2/stage20/constants.py may
    define LABEL_TO_STATE_MAPPING_V0. Every other module imports
    it -- never rebinds.
    """

    hits = _find_mapping_rebinds()
    assert hits == [], (
        "LABEL_TO_STATE_MAPPING_V0 must not be rebound outside "
        "constants.py. Found:\n"
        + "\n".join(f"  {f}:{ln}" for f, ln in hits)
    )
