"""Phase 1 smoke test: Stage 16B CLI rejects an invocation with no arguments.

``--runtime-policy-path``, ``--db-path``, and ``--limit`` are all
``required=True`` in the argparse parser, so calling ``main([])`` triggers
argparse's default ``SystemExit(2)``. This test asserts only the non-zero
contract; per-flag and value-validation behavior is exercised in Phase 7's
``test_cli.py``.
"""

from __future__ import annotations

import pytest

from PHX2.stage16b.cli import main


def test_cli_with_no_args_exits_non_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    assert exc_info.value.code != 0
