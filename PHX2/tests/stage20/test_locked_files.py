"""Stage 20.2 locked-file integrity guards (Phase D).

Two locks:

  * ``input_validators.py`` byte-identical to the Phase A entry
    snapshot. The SHA-256 captured at Phase A is hard-coded here.
    Any modification to the file -- even whitespace -- flips the
    SHA and fails this test.

  * No CLI entry point anywhere under ``PHX2/stage20/``: AST-walk
    every production .py file and assert zero ``if __name__ ==
    "__main__":`` blocks. Stage 20 is library-only; CLI wrappers
    are out of scope.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib


# Phase A entry SHA-256 (captured during STEP 0). Operator-locked.
_LOCKED_INPUT_VALIDATORS_SHA256: str = (
    "ed74a6ffbcc2e60aca6daa51893c4f2a638459dc913db6bd00f8ad00d64d274f"
)


_INPUT_VALIDATORS_PATH = pathlib.Path("PHX2/stage20/input_validators.py")
_STAGE20_PROD_ROOT = pathlib.Path("PHX2/stage20")


def _compute_file_sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(65536)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def test_input_validators_py_sha_matches_phase_a_lock():
    """Hard Constraint #2: input_validators.py is locked.

    The recorded SHA-256 was captured at Phase A entry; any drift
    -- intentional or accidental -- fails this test.
    """

    actual = _compute_file_sha256(_INPUT_VALIDATORS_PATH)
    assert actual == _LOCKED_INPUT_VALIDATORS_SHA256, (
        f"input_validators.py lock broken!\n"
        f"  Phase A entry SHA-256: {_LOCKED_INPUT_VALIDATORS_SHA256}\n"
        f"  Current   SHA-256:     {actual}"
    )


def test_input_validators_py_exists_and_is_readable():
    """Pair guard for the SHA test -- a missing file would fail
    the SHA test with a less obvious error.
    """

    assert _INPUT_VALIDATORS_PATH.exists(), (
        f"input_validators.py vanished: {_INPUT_VALIDATORS_PATH}"
    )
    assert _INPUT_VALIDATORS_PATH.stat().st_size > 0


def _find_main_blocks() -> list[tuple[str, int]]:
    """Return every ``if __name__ == "__main__":`` block under
    Stage 20 production code.
    """

    hits: list[tuple[str, int]] = []
    for f in sorted(_STAGE20_PROD_ROOT.rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.If):
                continue
            test = node.test
            if (
                isinstance(test, ast.Compare)
                and isinstance(test.left, ast.Name)
                and test.left.id == "__name__"
            ):
                for c in test.comparators:
                    if (
                        isinstance(c, ast.Constant)
                        and c.value == "__main__"
                    ):
                        hits.append((str(f), node.lineno))
    return hits


# Stage 20.4 closure layer has a sanctioned operator-facing CLI entry point
# per locked Stage 20.4 Section C.2:
#   python -m PHX2.stage20.closure.run_orchestrator <config.json>
# The exclusion is limited to PHX2/stage20/closure/.
# Stage 20.1/20.2/20.3 modules remain bound by the no-CLI constraint.
_NO_CLI_BLOCK_EXCLUDED_SUBTREE = pathlib.Path("PHX2/stage20/closure")


def test_no_cli_main_block_in_stage20_production():
    """Hard Constraint #5: no CLI entry point.

    AST-walk PHX2/stage20/**/*.py for ``if __name__ ==
    "__main__":`` blocks. Stage 20.1/20.2/20.3 modules remain
    library-only.

    Phase 6 exemption (locked Stage 20.4 Section C.2): files under
    ``PHX2/stage20/closure/`` are allowed to carry a ``__main__``
    block because the closure layer is the only sanctioned
    operator-facing CLI entry point in Stage 20
    (``python -m PHX2.stage20.closure.run_orchestrator <config>``).
    The exemption is narrow: it covers only the closure subtree.
    """

    hits = _find_main_blocks()
    excluded_str = str(_NO_CLI_BLOCK_EXCLUDED_SUBTREE)
    unexpected = [
        (p, ln) for (p, ln) in hits
        if not p.replace("\\", "/").startswith(
            excluded_str.replace("\\", "/") + "/"
        )
    ]
    assert unexpected == [], (
        "CLI __main__ block(s) found under PHX2/stage20/ "
        "outside the sanctioned Stage 20.4 closure exemption:\n"
        + "\n".join(f"  {p}:{ln}" for p, ln in unexpected)
    )
