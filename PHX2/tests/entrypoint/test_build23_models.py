"""Build #23 launcher MODEL-layer tests (pure; no I/O, no send).

Covers the durable-ledger baseline triple semantics (sha256 / size_bytes /
line_count), verbatim passthrough, redaction, the closed-set mode / action /
post-send / outcome vocabularies, and the routing / handoff denylists. The
current baseline `78D2...96 / 1096 / 3` is asserted as a model fact; nothing is
sent and the durable ledger is never touched.
"""

from __future__ import annotations

import dataclasses

import pytest

from PHX2.entrypoint import launcher_models as M


# The current operator baseline (sha256 / size_bytes / line_count).
BASELINE_SHA: str = (
    "78D20A7A2FE69BEF8BF833B60BB92209D06D23CE69A8D6F2800F991AC0331D96"
)
BASELINE: str = f"{BASELINE_SHA}:1096:3"


# ---------------------------------------------------------------------------
# Baseline parse / passthrough / redaction (the corrected exact semantics)
# ---------------------------------------------------------------------------


def test_current_baseline_parses_to_exact_triple() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    assert triple is not None
    assert triple.sha256 == BASELINE_SHA
    assert triple.size_bytes == 1096
    assert triple.line_count == 3


def test_baseline_passthrough_round_trips_verbatim() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    assert triple is not None
    # Passed through exactly as sha256:size_bytes:line_count.
    assert M.baseline_passthrough(triple) == BASELINE


def test_redacted_baseline_hides_the_full_digest() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    assert triple is not None
    display = M.redacted_baseline(triple)
    assert ".." in display
    assert display.endswith(":1096:3")
    # The full 64-hex digest never appears in the redacted display.
    assert BASELINE_SHA not in display
    assert display.startswith(BASELINE_SHA[:8])


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "not-a-triple",
        BASELINE_SHA,  # missing the two counts
        f"{BASELINE_SHA}:1096",  # only two parts
        f"{BASELINE_SHA}:1096:3:4",  # four parts
        f"{BASELINE_SHA[:-1]}:1096:3",  # 63-char sha
        f"{BASELINE_SHA}G:1096:3",  # 65 chars / non-hex
        f"{BASELINE_SHA[:-1]}z:1096:3",  # non-hex char
        f"{BASELINE_SHA}:-1:3",  # negative size
        f"{BASELINE_SHA}:10.5:3",  # non-integer size
        f"{BASELINE_SHA}:01096:3",  # non-canonical leading zero
        f"{BASELINE_SHA}:1096:03",  # non-canonical leading zero
        f"{BASELINE_SHA}:1096: 3",  # whitespace
        f"{BASELINE_SHA}:1096:three",  # non-numeric
    ],
)
def test_malformed_baseline_fails_closed(raw: object) -> None:
    assert M.parse_baseline_triple(raw) is None


def test_zero_counts_are_canonical_and_accepted() -> None:
    triple = M.parse_baseline_triple(f"{BASELINE_SHA}:0:0")
    assert triple is not None
    assert triple.size_bytes == 0
    assert triple.line_count == 0


def test_lowercase_sha_is_accepted_and_case_preserved() -> None:
    lowered = BASELINE_SHA.lower()
    triple = M.parse_baseline_triple(f"{lowered}:1096:3")
    assert triple is not None
    assert triple.sha256 == lowered  # case preserved for verbatim passthrough


def test_baseline_triple_is_immutable() -> None:
    triple = M.parse_baseline_triple(BASELINE)
    assert triple is not None
    with pytest.raises(dataclasses.FrozenInstanceError):
        triple.line_count = 4  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Closed-set vocabularies
# ---------------------------------------------------------------------------


def test_only_private_supervised_mode_is_supported() -> None:
    assert M.SUPPORTED_MODES == ("private-supervised",)
    assert M.is_supported_mode("private-supervised") is True
    for bad in ("public", "subscriber", "paid", "", None, "PRIVATE-SUPERVISED"):
        assert M.is_supported_mode(bad) is False


def test_supported_actions_are_the_three_no_send_or_launch_actions() -> None:
    assert M.SUPPORTED_ACTIONS == ("preflight-only", "dry-run", "live")
    for good in M.SUPPORTED_ACTIONS:
        assert M.is_supported_action(good) is True
    for bad in ("send", "arm", "", None):
        assert M.is_supported_action(bad) is False


def test_post_send_only_stop() -> None:
    assert M.SUPPORTED_POST_SEND == ("stop",)
    assert M.is_supported_post_send("stop") is True
    assert M.is_supported_post_send("continue") is False


def test_outcomes_are_closed_set() -> None:
    assert M.OUTCOME_SAFE_NOOP in M.SUPPORTED_OUTCOMES
    assert M.OUTCOME_INVOKED_SUPERVISOR in M.SUPPORTED_OUTCOMES
    for outcome in M.SUPPORTED_OUTCOMES:
        assert M.is_launch_outcome(outcome) is True
    assert M.is_launch_outcome("SOMETHING_ELSE") is False


def test_supervisor_env_pointer_name_is_the_owned_pointer() -> None:
    assert M.SUPERVISOR_COMMAND_ENV == "PHX2_SUPERVISOR_CMD"


# ---------------------------------------------------------------------------
# Denylists guard private-only, no-arm/transport handoffs
# ---------------------------------------------------------------------------


def test_routing_denylist_covers_public_and_subscriber() -> None:
    for token in ("public", "subscriber", "paid", "broadcast"):
        assert token in M.FORBIDDEN_ROUTING_TOKENS


def test_handoff_flag_denylist_covers_arm_and_transport() -> None:
    for flag in ("--arm", "--inject-transport", "--transport", "--authorize"):
        assert flag in M.FORBIDDEN_HANDOFF_FLAGS
    # The legitimate post-send flag is NOT on the denylist.
    assert M.HANDOFF_POST_SEND_FLAG not in M.FORBIDDEN_HANDOFF_FLAGS


def test_exit_codes() -> None:
    assert M.EXIT_OK == 0
    assert M.EXIT_REFUSED != 0
