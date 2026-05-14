"""Stage 19 git helper. Sole consumer of subprocess in Stage 19.

Provides ``get_git_commit()`` which captures the current HEAD as
a 40-hex SHA via ``git rev-parse HEAD``, returning ``"unknown"``
on any failure (missing git, non-git directory, malformed
output, timeout, or any unexpected exception).

The file name ``_git.py`` and the underscore prefix advertise
its impurity. The static AST check in
``PHX2/tests/stage19/test_import_boundaries.py`` relies on this
filename to scope the subprocess allowance for Stage 19; every
other Stage 19 production file remains subprocess-free.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


_SHA_PATTERN: re.Pattern[str] = re.compile(r"^[0-9a-f]{40}$")


def get_git_commit() -> str:
    """Return the current HEAD as a 40-hex lowercase SHA, or
    ``"unknown"`` on any failure.

    Failure modes that yield ``"unknown"``:
      * ``git`` not installed (FileNotFoundError)
      * non-zero exit (CalledProcessError raised because
        ``check=True``)
      * timeout exceeded (TimeoutExpired)
      * other OS errors (OSError)
      * any unexpected Exception
      * malformed output (not exactly 40 lowercase hex chars)
    """

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=str(Path(__file__).resolve().parent),
            check=True,
        )
    except FileNotFoundError:
        return "unknown"
    except subprocess.CalledProcessError:
        return "unknown"
    except subprocess.TimeoutExpired:
        return "unknown"
    except OSError:
        return "unknown"
    except Exception:
        return "unknown"

    sha = (result.stdout or "").strip()
    if not _SHA_PATTERN.match(sha):
        return "unknown"
    return sha


__all__ = ["get_git_commit"]
