"""Stage 24.5 no-confirmed-router-fee-decoder lock (Path B).

Stage 24.5 took Path B per ``PHX2/docs/STAGE_24_BRAINSTORM.md``
Section 5 / Section 15 / Section 19: no sanitized real Axiom /
FLASHX8 transaction fixtures exist to prove the instruction
layout, account layout, fee-account movement, lamport / token
flow, and instruction location that Section 9 requires before a
router / global-fee primitive can be promoted to
``decoder_status=DECODED``. The router / global-fee surface
therefore stays at the Stage 24.4 candidate-only contract.

This module pins:

  * The Stage 24.5 scalar marker constants are ``False`` / ``0``.
  * The Stage 24.5 lock doc exists at the expected path and
    carries the documented honesty claims.
  * ``router_fee.py`` carries no confirmed-decoder symbols (no
    ``decode_router_fee_confirmed``, no
    ``decode_axiom_global_fee``, no ``FEE_SOURCE_AXIOM_GLOBAL_FEE``
    constant usage, no ``DECODER_STATUS_DECODED`` constant usage).
  * The runtime decoder still emits candidate-only results for
    every active-router, deprecated-router, and no-router input:
    ``decoder_status != "DECODED"``, ``amount_lamports is None``,
    ``fee_source != "AXIOM_GLOBAL_FEE"``.
  * No sanitized real fixture has landed under
    ``PHX2/tests/stage24/fixtures/`` yet.
  * The Stage 24.5 file-scope boundary is held: no Stage 24.6 /
    24.7 production file (``execution_quality.py``, ``runner.py``,
    ``artifact_writer.py``, ``STAGE_24_CLOSURE_AUDIT.md``,
    ``STAGE_25_HANDOFF.md``) has been created.
  * ``router_fee.py`` has not been quietly rewritten: its decoder
    name and version axes still match the locked 24.4 strings.

The runtime-invariant checks below are deliberately redundant
with the Stage 24.4 invariants. Stage 24.5's contract is
precisely "the Stage 24.4 candidate-only semantics remain the
truth": deleting the Stage 24.4 candidate test file must not
silently re-enable promotion to ``DECODED``.

When a future Stage 24.x sub-stage attempts Path A, every check
in this file is the explicit drift point and must be updated in
the same patch that adds the confirmed decoder, the sanitized
real fixtures, and the lock-doc rewrite.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PHX2.stage24 import constants as c
from PHX2.stage24 import router_fee as router_fee_mod
from PHX2.stage24.router_fee import decode_router_fee_candidate
from PHX2.tests.stage24.fixtures.builders import (
    make_axiom_flashx8_instruction,
    make_axiom_trading_program_1_instruction,
    make_deprecated_axiom_instruction,
    make_execution_input,
    make_router_like_execution_input,
)


# ---------------------------------------------------------------------------
# Locked paths
# ---------------------------------------------------------------------------


_STAGE_24_PRODUCTION_ROOT: Path = Path(router_fee_mod.__file__).parent
_STAGE_24_LOCK_DOC_PATH: Path = (
    _STAGE_24_PRODUCTION_ROOT / "STAGE_24_5_NO_DECODER_LOCK.md"
)
_STAGE_24_FIXTURES_ROOT: Path = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Scalar marker constants
# ---------------------------------------------------------------------------


def test_stage_24_5_has_confirmed_router_fee_decoder_is_false():
    assert c.STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER is False


def test_stage_24_5_has_confirmed_router_fee_decoder_is_bool():
    assert isinstance(c.STAGE_24_5_HAS_CONFIRMED_ROUTER_FEE_DECODER, bool)


def test_stage_24_5_real_fixture_count_is_zero():
    assert c.STAGE_24_5_REAL_FIXTURE_COUNT == 0


def test_stage_24_5_real_fixture_count_is_int():
    assert isinstance(c.STAGE_24_5_REAL_FIXTURE_COUNT, int)
    assert not isinstance(c.STAGE_24_5_REAL_FIXTURE_COUNT, bool)


def test_stage_24_5_confirmed_layout_count_is_zero():
    assert c.STAGE_24_5_CONFIRMED_LAYOUT_COUNT == 0


def test_stage_24_5_confirmed_layout_count_is_int():
    assert isinstance(c.STAGE_24_5_CONFIRMED_LAYOUT_COUNT, int)
    assert not isinstance(c.STAGE_24_5_CONFIRMED_LAYOUT_COUNT, bool)


# ---------------------------------------------------------------------------
# Lock doc
# ---------------------------------------------------------------------------


def _read_lock_doc() -> str:
    assert _STAGE_24_LOCK_DOC_PATH.is_file(), (
        f"Stage 24.5 lock doc missing at {_STAGE_24_LOCK_DOC_PATH}"
    )
    return _STAGE_24_LOCK_DOC_PATH.read_text(encoding="utf-8")


def test_stage_24_5_lock_doc_exists():
    assert _STAGE_24_LOCK_DOC_PATH.is_file()


def test_stage_24_5_lock_doc_names_path_b():
    text = _read_lock_doc()
    assert "Path B" in text


def test_stage_24_5_lock_doc_states_no_confirmed_router_global_fee_decoder():
    text = _read_lock_doc().lower()
    assert "no confirmed" in text
    assert ("router" in text) or ("global-fee" in text) or (
        "global fee" in text
    )


def test_stage_24_5_lock_doc_forbids_fake_zero():
    text = _read_lock_doc().lower()
    assert "no fake zero" in text


def test_stage_24_5_lock_doc_states_amount_lamports_remains_none():
    text = _read_lock_doc()
    assert "amount_lamports" in text
    assert "None" in text


def test_stage_24_5_lock_doc_forbids_decoded_router_fee_status():
    text = _read_lock_doc()
    assert "DECODED" in text
    lowered = text.lower()
    assert ("router_fee" in lowered) or ("router-fee" in lowered)


def test_stage_24_5_lock_doc_states_stage_24_6_emits_candidate_artifacts():
    text = _read_lock_doc()
    assert "24.6" in text
    assert "candidate" in text.lower()


# ---------------------------------------------------------------------------
# router_fee.py source inspection (no confirmed decoder symbols)
# ---------------------------------------------------------------------------


def _router_fee_source() -> str:
    return Path(router_fee_mod.__file__).read_text(encoding="utf-8")


def _router_fee_identifiers() -> set[str]:
    tree = ast.parse(_router_fee_source())
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
        elif isinstance(node, ast.alias):
            idents.add(node.name)
            if node.asname:
                idents.add(node.asname)
    return idents


def _router_fee_function_def_names() -> set[str]:
    tree = ast.parse(_router_fee_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def test_router_fee_has_no_decode_router_fee_confirmed_function():
    assert (
        "decode_router_fee_confirmed"
        not in _router_fee_function_def_names()
    )


def test_router_fee_has_no_decode_axiom_global_fee_function():
    assert (
        "decode_axiom_global_fee" not in _router_fee_function_def_names()
    )


def test_router_fee_does_not_reference_decode_router_fee_confirmed():
    assert "decode_router_fee_confirmed" not in _router_fee_identifiers()


def test_router_fee_does_not_reference_decode_axiom_global_fee():
    assert "decode_axiom_global_fee" not in _router_fee_identifiers()


def test_router_fee_does_not_export_decode_router_fee_confirmed_callable():
    assert not hasattr(router_fee_mod, "decode_router_fee_confirmed")


def test_router_fee_does_not_export_decode_axiom_global_fee_callable():
    assert not hasattr(router_fee_mod, "decode_axiom_global_fee")


def test_router_fee_does_not_use_confirmed_axiom_global_fee_constant():
    # Only the ``_CANDIDATE`` variant is allowed. The decoded
    # ``FEE_SOURCE_AXIOM_GLOBAL_FEE`` identifier must not appear
    # as an imported or referenced name.
    assert "FEE_SOURCE_AXIOM_GLOBAL_FEE" not in _router_fee_identifiers()


def test_router_fee_does_not_use_decoder_status_decoded_constant():
    assert "DECODER_STATUS_DECODED" not in _router_fee_identifiers()


def test_router_fee_decoder_name_is_still_the_locked_stage_24_4_string():
    assert (
        router_fee_mod.ROUTER_FEE_DECODER_NAME == "router_fee_candidate_v0"
    )


def test_router_fee_decoder_version_is_still_the_locked_stage_24_4_string():
    assert (
        router_fee_mod.ROUTER_FEE_DECODER_VERSION
        == "stage24_v0_router_fee_candidate"
    )


# ---------------------------------------------------------------------------
# Runtime candidate-only invariant
# ---------------------------------------------------------------------------


def _stage_24_5_required_router_inputs():
    """Build the four required Stage 24.5 lock-test execution inputs."""
    return (
        # No router present anywhere (default ComputeBudget instruction).
        make_execution_input(),
        # Active FLASHX8 router candidate.
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        ),
        # Active Axiom Trading Program 1 candidate.
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_trading_program_1_instruction(),
            ),
        ),
        # Deprecated Axiom router.
        make_router_like_execution_input(
            top_level_instructions=(
                make_deprecated_axiom_instruction(deprecated_index=0),
            ),
        ),
    )


def test_decoder_status_is_never_decoded_in_stage_24_5():
    for execution_input in _stage_24_5_required_router_inputs():
        result = decode_router_fee_candidate(execution_input)
        assert result.decoder_status != "DECODED"


def test_amount_lamports_is_always_none_in_stage_24_5():
    for execution_input in _stage_24_5_required_router_inputs():
        result = decode_router_fee_candidate(execution_input)
        assert result.amount_lamports is None
        assert result.amount_token is None
        assert result.mint == ""


def test_fee_source_never_confirmed_axiom_global_fee_in_stage_24_5():
    for execution_input in _stage_24_5_required_router_inputs():
        result = decode_router_fee_candidate(execution_input)
        assert result.fee_source != "AXIOM_GLOBAL_FEE"
        assert result.fee_source != "ROUTER_FEE"


def test_active_router_paths_use_candidate_fee_sources_only_in_stage_24_5():
    allowed_active_fee_sources: frozenset[str] = frozenset(
        {"AXIOM_GLOBAL_FEE_CANDIDATE", "ROUTER_FEE_CANDIDATE"}
    )
    active_inputs = (
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        ),
        make_router_like_execution_input(
            top_level_instructions=(
                make_axiom_trading_program_1_instruction(),
            ),
        ),
    )
    for execution_input in active_inputs:
        result = decode_router_fee_candidate(execution_input)
        assert result.fee_source in allowed_active_fee_sources


def test_no_router_input_remains_absent_in_stage_24_5():
    result = decode_router_fee_candidate(make_execution_input())
    assert result.decoder_status in {"ABSENT", "NOT_APPLICABLE"}
    assert result.fee_source == "UNKNOWN"
    assert result.amount_lamports is None


def test_deprecated_router_input_remains_unsupported_in_stage_24_5():
    execution_input = make_router_like_execution_input(
        top_level_instructions=(
            make_deprecated_axiom_instruction(deprecated_index=0),
        ),
    )
    result = decode_router_fee_candidate(execution_input)
    assert result.decoder_status == "UNSUPPORTED"
    assert result.fee_source == "ROUTER_FEE_CANDIDATE"
    assert result.amount_lamports is None


# ---------------------------------------------------------------------------
# No sanitized real fixtures yet
# ---------------------------------------------------------------------------
#
# This guard is local to Stage 24.5. A future Path A patch must
# update or remove the substrings tuple in the same change that
# lands sanitized real fixtures, the confirmed decoder, and the
# rewritten lock doc.


_STAGE_24_5_FORBIDDEN_FIXTURE_BASENAME_SUBSTRINGS: tuple[str, ...] = (
    "sanitized",
    "real",
    "axiom_capture",
    "flashx8_capture",
)


_STAGE_24_5_FORBIDDEN_FIXTURE_DIRECTORY_SUBSTRINGS: tuple[str, ...] = (
    "sanitized",
    "sanitized_real",
    "axiom_capture",
    "flashx8_capture",
)


def test_stage_24_fixtures_root_exists():
    assert _STAGE_24_FIXTURES_ROOT.is_dir(), (
        f"Stage 24 fixtures root missing at {_STAGE_24_FIXTURES_ROOT}"
    )


def test_no_sanitized_real_directory_under_stage_24_fixtures():
    if not _STAGE_24_FIXTURES_ROOT.is_dir():
        return
    for path in _STAGE_24_FIXTURES_ROOT.rglob("*"):
        if not path.is_dir():
            continue
        name = path.name.lower()
        for forbidden in _STAGE_24_5_FORBIDDEN_FIXTURE_DIRECTORY_SUBSTRINGS:
            assert forbidden not in name, (
                f"Stage 24.5 lock: forbidden fixture directory {path} "
                f"contains substring {forbidden!r}. Sanitized real "
                "fixtures are not allowed until Path A is attempted."
            )


def test_no_sanitized_real_files_under_stage_24_fixtures():
    if not _STAGE_24_FIXTURES_ROOT.is_dir():
        return
    for path in _STAGE_24_FIXTURES_ROOT.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        for forbidden in _STAGE_24_5_FORBIDDEN_FIXTURE_BASENAME_SUBSTRINGS:
            assert forbidden not in name, (
                f"Stage 24.5 lock: forbidden fixture file {path} carries "
                f"substring {forbidden!r}. Sanitized real fixtures are "
                "not allowed until Path A is attempted."
            )


def test_real_fixture_count_constant_matches_disk_state():
    # The fixture-count constant claims zero sanitized real
    # fixtures. The on-disk scan above asserts the same. This
    # test cross-pins them so a future Path A patch that bumps
    # the constant without adding fixtures (or vice versa) fails.
    if not _STAGE_24_FIXTURES_ROOT.is_dir():
        observed = 0
    else:
        observed = 0
        for path in _STAGE_24_FIXTURES_ROOT.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            if any(
                needle in name
                for needle in _STAGE_24_5_FORBIDDEN_FIXTURE_BASENAME_SUBSTRINGS
            ):
                observed += 1
    assert observed == c.STAGE_24_5_REAL_FIXTURE_COUNT == 0


# ---------------------------------------------------------------------------
# Boundary: no Stage 24.6 / 24.7 production files at Stage 24.5
# ---------------------------------------------------------------------------


_STAGE_24_5_FORBIDDEN_PRODUCTION_FILENAMES: tuple[str, ...] = (
    # Stage 24.6 runner / writer / quality surface.
    "execution_quality.py",
    "runner.py",
    "artifact_writer.py",
    "stage24_runner.py",
    "evaluations_writer.py",
    "summary_writer.py",
    "csv_writer.py",
    # Stage 24.7 closure docs.
    "STAGE_24_CLOSURE_AUDIT.md",
    "STAGE_25_HANDOFF.md",
)


def test_stage_24_5_does_not_create_stage_24_6_or_24_7_production_files():
    for name in _STAGE_24_5_FORBIDDEN_PRODUCTION_FILENAMES:
        path = _STAGE_24_PRODUCTION_ROOT / name
        assert not path.exists(), (
            f"Stage 24.5 boundary violation: {name} must not exist yet"
        )


def test_stage_24_5_does_not_introduce_runner_or_writer_subdirectory():
    forbidden_subdir_names: tuple[str, ...] = (
        "decoders",
        "runners",
        "writers",
        "transports",
        "adapters",
    )
    for name in forbidden_subdir_names:
        path = _STAGE_24_PRODUCTION_ROOT / name
        assert not path.exists(), (
            f"Stage 24.5 boundary violation: subdirectory {name!r} must "
            "not exist"
        )


def test_stage_24_5_lock_doc_filename_is_pinned():
    # The lock-doc filename is part of the contract: the Stage
    # 24.5 lock doc must live at this exact path so future audits
    # can find it without a search.
    assert _STAGE_24_LOCK_DOC_PATH.name == "STAGE_24_5_NO_DECODER_LOCK.md"


def test_router_fee_module_has_not_been_replaced_by_a_runner_or_writer():
    # The decoder name / version axes are the canonical anchor.
    # If either string has drifted, the patch is mis-scoped and
    # this test should be the first failure a future Path A
    # patch encounters.
    assert (
        router_fee_mod.ROUTER_FEE_DECODER_NAME == "router_fee_candidate_v0"
    )
    assert (
        router_fee_mod.ROUTER_FEE_DECODER_VERSION
        == "stage24_v0_router_fee_candidate"
    )
    # The public callable still emits candidates.
    result = decode_router_fee_candidate(
        make_router_like_execution_input(
            top_level_instructions=(make_axiom_flashx8_instruction(),),
        )
    )
    assert result.decoder_status != "DECODED"
    assert result.amount_lamports is None
