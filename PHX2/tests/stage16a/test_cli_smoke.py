"""Phase 1 smoke test: Stage 16A CLI exits non-zero when no args are provided.

This is the only Phase 1 test. It confirms the CLI module is importable
and that argparse's required-flag enforcement is wired correctly. Later
phases add the load-time, build-time, and three-tier exit tests.
"""

from __future__ import annotations

import pytest

from PHX2.stage16a.cli import main


def test_cli_no_args_exits_non_zero() -> None:
    with pytest.raises(SystemExit) as exc_info:
        main([])
    code = exc_info.value.code
    assert code is not None and code != 0, (
        f"Stage 16A CLI must exit non-zero when no args are supplied; got code={code!r}"
    )
