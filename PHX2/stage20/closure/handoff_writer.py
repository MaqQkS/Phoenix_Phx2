"""Stage 20.4 handoff doc + README renderer.

Renders ``stage21_handoff.md`` and ``README.md`` from locked
templates living in ``PHX2/stage20/closure/templates/``. Both
renderers use the same deterministic ``{{placeholder}}``
substitution mechanism and assert that no unfilled
placeholders remain in the output.

Public surface:

  * ``render_handoff(inputs, run_id) -> str``
  * ``render_readme(inputs, run_id, closure_status) -> str``
  * ``find_unfilled_placeholders(text) -> tuple[str, ...]``

The templates are excluded from the codebase auditor's token
scan (per the ``/templates/`` exclusion in
``PHX2.stage20.closure.codebase_auditor``), so the locked
section text in the handoff template may reference safety-flag
field names in prose without tripping E2040.

What this module does NOT do:
  * No file I/O (caller is closure_writer / orchestrator).
  * No git / subprocess / env reads / network.
  * No alternate template paths; the path is locked at
    ``PHX2/stage20/closure/templates/stage21_handoff.md.tmpl``.

Phoenix1 departure note: this module imports no Phoenix1 code.
The handoff template references Phoenix1 as a forbidden import
target in Stage 21 (Section D's locked text).

Known limitations
-----------------
  * Template rendering uses simple ``{{placeholder}}`` exact-key
    substitution; nested placeholders (e.g. a placeholder whose
    value contains another ``{{key}}``) are not supported, and
    placeholder values must be string-coercible scalars.
  * Section text is template-locked. Wording changes (Section A
    through Section H, the manual-tag recommendation, the
    locked next-steps numbering) require editing the template
    files under ``PHX2/stage20/closure/templates/``; they cannot
    be altered via config or runtime input.
"""

from __future__ import annotations

import re
from pathlib import Path

from PHX2.stage20.closure.constants import (
    HANDOFF_CONTRACT_VERSION,
    STAGE20_4_MINOR_VERSION,
)
from PHX2.stage20.closure.models import ClosureInputConfig


_TEMPLATES_DIR = Path(__file__).parent / "templates"
_HANDOFF_TEMPLATE_PATH = _TEMPLATES_DIR / "stage21_handoff.md.tmpl"
_README_TEMPLATE_PATH = _TEMPLATES_DIR / "readme.md.tmpl"


_PLACEHOLDER_PATTERN = re.compile(r"\{\{[^}]+\}\}")


def _load_template(path: Path) -> str:
    """Read template text. Read-only access; no caller-supplied path."""

    return path.read_text(encoding="utf-8")


def _substitute(text: str, substitutions: dict) -> str:
    """Replace every ``{{key}}`` in ``text`` with the string value
    from ``substitutions[key]``.

    Iteration order over ``substitutions`` does not affect the
    output -- replacement is exact-match per key. The caller is
    responsible for ensuring every placeholder in the template
    has a corresponding key (otherwise unfilled placeholders
    survive and trigger the post-render assertion).
    """

    out = text
    for key, value in substitutions.items():
        out = out.replace("{{" + key + "}}", str(value))
    return out


def find_unfilled_placeholders(text: str) -> tuple:
    """Return a tuple of every ``{{<x>}}`` substring still present
    in ``text``. Empty tuple means every placeholder was filled."""

    return tuple(_PLACEHOLDER_PATTERN.findall(text))


def _assert_no_unfilled(text: str, context: str) -> None:
    leftover = find_unfilled_placeholders(text)
    if leftover:
        raise RuntimeError(
            f"{context}: unfilled placeholders remain in rendered "
            f"output: {list(leftover)}"
        )


def render_handoff(
    *,
    inputs: ClosureInputConfig,
    run_id: str,
) -> str:
    """Render ``stage21_handoff.md`` from the locked template.

    Placeholders filled:
      * contract_version, run_id, generated_at_utc
      * stage20_1_commit_sha, stage20_2_commit_sha,
        stage20_3_commit_sha
      * operator_test_command, operator_run1_passed,
        operator_run2_passed, operator_both_runs_match,
        operator_all_green

    Returns the rendered string. Raises ``RuntimeError`` if any
    ``{{placeholder}}`` survived substitution.
    """

    template = _load_template(_HANDOFF_TEMPLATE_PATH)
    subs = {
        "contract_version": HANDOFF_CONTRACT_VERSION,
        "run_id": run_id,
        "generated_at_utc": inputs.generated_at_utc,
        "stage20_1_commit_sha": inputs.stage20_1_commit_sha,
        "stage20_2_commit_sha": inputs.stage20_2_commit_sha,
        "stage20_3_commit_sha": inputs.stage20_3_commit_sha,
        "operator_test_command": (
            inputs.operator_test_results.test_command
        ),
        "operator_run1_passed": inputs.operator_test_results.run1_passed,
        "operator_run2_passed": inputs.operator_test_results.run2_passed,
        "operator_both_runs_match": (
            "true"
            if inputs.operator_test_results.both_runs_match
            else "false"
        ),
        "operator_all_green": (
            "true"
            if inputs.operator_test_results.all_green
            else "false"
        ),
    }
    rendered = _substitute(template, subs)
    _assert_no_unfilled(rendered, "handoff render")
    return rendered


def render_readme(
    *,
    inputs: ClosureInputConfig,
    run_id: str,
    closure_status: str,
) -> str:
    """Render the closure ``README.md`` from the locked template.

    Placeholders filled:
      * run_id, generated_at_utc, stage20_4_minor_version,
        handoff_contract_version, closure_status

    Returns the rendered string. Raises ``RuntimeError`` if any
    ``{{placeholder}}`` survived substitution.
    """

    template = _load_template(_README_TEMPLATE_PATH)
    subs = {
        "run_id": run_id,
        "generated_at_utc": inputs.generated_at_utc,
        "stage20_4_minor_version": STAGE20_4_MINOR_VERSION,
        "handoff_contract_version": HANDOFF_CONTRACT_VERSION,
        "closure_status": closure_status,
    }
    rendered = _substitute(template, subs)
    _assert_no_unfilled(rendered, "readme render")
    return rendered


__all__ = [
    "find_unfilled_placeholders",
    "render_handoff",
    "render_readme",
]
