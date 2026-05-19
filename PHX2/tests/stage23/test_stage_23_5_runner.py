"""Stage 23.5 unified runner tests.

Pins the contract of ``PHX2.stage23.runner.run_stage23_filters``:

  * Default filter set is the three landed Stage 23 filters.
  * One input -> three evaluations (one per filter).
  * Multiple inputs -> input_count * filter_count evaluations.
  * Each filter is called exactly once per input.
  * A filter returning ``MISSING_INPUT`` / ``UNKNOWN`` /
    ``UNSUPPORTED`` for a given input does NOT block the other
    filters from evaluating that same input.
  * Deterministic ordering across repeated runs.
  * Same inputs + same ``created_at_utc`` -> identical
    ``input_hash`` / ``evaluation_hash`` on every evaluation.
  * Changing the input mutates relevant hashes.
  * ``label_counts`` / ``data_status_counts`` /
    ``reason_code_counts`` reflect the evaluation outputs.
  * Input objects are not mutated.
  * ``filter_version`` and ``threshold_version`` are retained
    separately per filter.
  * Every emitted label / data_status / filter_family is a
    member of its closed set.
  * Typed ``Stage23Error`` raised by a filter is caught and
    rendered as a deterministic ``UNKNOWN`` / ``MISSING``
    evaluation; untyped errors propagate.
"""

from __future__ import annotations

from typing import Mapping

import pytest

from PHX2.stage23.constants import (
    DATA_STATUSES,
    DATA_STATUS_MISSING,
    DATA_STATUS_UNSUPPORTED,
    FILTER_FAMILIES,
    FILTER_FAMILY_HOLDER_CONCENTRATION,
    FILTER_FAMILY_LAUNCH_STRUCTURE,
    FILTER_FAMILY_WALLET_SOURCE_QUALITY,
    LABELS,
    LABEL_MISSING_INPUT,
    LABEL_UNKNOWN,
)
from PHX2.stage23.errors import Stage23ContractError, Stage23Error
from PHX2.stage23.holder_concentration import HolderConcentrationFilter
from PHX2.stage23.launch_structure import LaunchStructureFilter
from PHX2.stage23.models import Stage23FilterInput, Stage23FilterResult
from PHX2.stage23.runner import (
    REASON_STAGE23_FILTER_RAISED_ERROR,
    STAGE23_RUNNER_REASON_CODES,
    Stage23RunnerResult,
    default_filters,
    run_stage23_filters,
)
from PHX2.stage23.wallet_source_quality import WalletSourceQualityFilter
from PHX2.tests.stage23.fixtures.builders import (
    FIXED_CLOCK_UTC,
    empty_payload_summary,
    make_filter_input,
    make_mixed_filter_input,
    make_mixed_payload_summary,
    make_unsupported_holder_payload_summary,
    make_unsupported_launch_payload_summary,
    make_unsupported_wallet_source_payload_summary,
)


_DEFAULT_FILTER_COUNT: int = 3


# ---------------------------------------------------------------------------
# Default filter set
# ---------------------------------------------------------------------------


def test_default_filters_returns_three_filters():
    filters = default_filters()
    assert len(filters) == _DEFAULT_FILTER_COUNT


def test_default_filters_identities_are_locked():
    filters = default_filters()
    names = tuple(f.filter_name for f in filters)
    assert names == (
        "holder_concentration",
        "launch_structure",
        "wallet_source_quality",
    )


def test_default_filters_families_are_locked_closed_set_members():
    filters = default_filters()
    for filter_obj in filters:
        assert filter_obj.filter_family in FILTER_FAMILIES


def test_default_filters_versions_are_distinct_per_filter():
    filters = default_filters()
    versions = {f.filter_version for f in filters}
    assert len(versions) == _DEFAULT_FILTER_COUNT


def test_default_filters_threshold_versions_share_observe_only_token():
    filters = default_filters()
    for f in filters:
        assert f.threshold_version == "thresholds_v0_observe_only"


# ---------------------------------------------------------------------------
# One input -> three evaluations
# ---------------------------------------------------------------------------


def test_one_input_produces_three_evaluations():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.input_count == 1
    assert result.evaluation_count == 3
    assert result.filter_count == _DEFAULT_FILTER_COUNT
    assert len(result.evaluations) == 3


def test_one_input_invokes_each_filter_exactly_once():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    filter_names = tuple(
        ev.filter_result.filter_name for ev in result.evaluations
    )
    assert sorted(filter_names) == [
        "holder_concentration",
        "launch_structure",
        "wallet_source_quality",
    ]


def test_one_input_each_evaluation_carries_distinct_filter_family():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    families = {
        ev.filter_result.filter_family for ev in result.evaluations
    }
    assert families == {
        FILTER_FAMILY_HOLDER_CONCENTRATION,
        FILTER_FAMILY_LAUNCH_STRUCTURE,
        FILTER_FAMILY_WALLET_SOURCE_QUALITY,
    }


# ---------------------------------------------------------------------------
# Multiple inputs -> input_count * 3 evaluations
# ---------------------------------------------------------------------------


def test_multiple_inputs_produce_input_count_times_three_evaluations():
    inputs = [
        make_mixed_filter_input(token_mint="MintA", event_id="evt_a"),
        make_mixed_filter_input(token_mint="MintB", event_id="evt_b"),
        make_mixed_filter_input(token_mint="MintC", event_id="evt_c"),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.input_count == 3
    assert result.evaluation_count == 9


def test_each_input_yields_one_evaluation_per_filter():
    inputs = [
        make_mixed_filter_input(token_mint="MintA", event_id="evt_a"),
        make_mixed_filter_input(token_mint="MintB", event_id="evt_b"),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    # Group evaluations by (token_mint, filter_name) and confirm
    # each pair occurs exactly once.
    grouping: dict[tuple[str, str], int] = {}
    for ev in result.evaluations:
        key = (
            ev.filter_input.token_mint,
            ev.filter_result.filter_name,
        )
        grouping[key] = grouping.get(key, 0) + 1
    assert all(count == 1 for count in grouping.values())
    assert len(grouping) == 6


# ---------------------------------------------------------------------------
# Per-family missing primitives must not block other families
# ---------------------------------------------------------------------------


def test_unsupported_holder_does_not_block_launch_or_wallet():
    """When only the holder sub-family is unsupported, the runner
    should still produce evaluations for launch and wallet-source
    based on the available primitives in the payload.
    """
    payload = make_mixed_payload_summary(
        holder_overrides=make_unsupported_holder_payload_summary(),
    )
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input(payload_summary=payload)],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    names_to_labels = {
        ev.filter_result.filter_name: ev.filter_result.label
        for ev in result.evaluations
    }
    assert names_to_labels["holder_concentration"] == LABEL_UNKNOWN
    # The launch and wallet-source filters should still produce
    # a verdict (not be skipped).
    assert "launch_structure" in names_to_labels
    assert "wallet_source_quality" in names_to_labels


def test_unsupported_wallet_does_not_block_holder_or_launch():
    payload = make_mixed_payload_summary(
        wallet_source_overrides=make_unsupported_wallet_source_payload_summary(),
    )
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input(payload_summary=payload)],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    names_to_labels = {
        ev.filter_result.filter_name: ev.filter_result.label
        for ev in result.evaluations
    }
    assert names_to_labels["wallet_source_quality"] == LABEL_UNKNOWN
    assert "holder_concentration" in names_to_labels
    assert "launch_structure" in names_to_labels


def test_unsupported_launch_does_not_block_holder_or_wallet():
    payload = make_mixed_payload_summary(
        launch_overrides=make_unsupported_launch_payload_summary(),
    )
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input(payload_summary=payload)],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    names_to_labels = {
        ev.filter_result.filter_name: ev.filter_result.label
        for ev in result.evaluations
    }
    assert names_to_labels["launch_structure"] == LABEL_UNKNOWN
    assert "holder_concentration" in names_to_labels
    assert "wallet_source_quality" in names_to_labels


def test_empty_payload_still_produces_three_evaluations():
    """An empty payload causes every filter to emit MISSING_INPUT
    or INSUFFICIENT_DATA, but the runner still produces one
    evaluation per filter rather than skipping.
    """
    result = run_stage23_filters(
        filter_inputs=[
            make_filter_input(payload_summary=empty_payload_summary()),
        ],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.input_count == 1
    assert result.evaluation_count == 3
    for ev in result.evaluations:
        assert ev.filter_result.label != "NORMAL"


# ---------------------------------------------------------------------------
# Deterministic ordering
# ---------------------------------------------------------------------------


def test_repeated_runs_produce_identical_evaluation_tuples():
    inputs = [
        make_mixed_filter_input(token_mint="MintZ", event_id="evt_z"),
        make_mixed_filter_input(token_mint="MintA", event_id="evt_a"),
    ]
    result_a = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    result_b = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result_a.evaluations == result_b.evaluations


def test_evaluations_sort_by_token_mint_then_event_then_captured_then_filter():
    inputs = [
        make_mixed_filter_input(token_mint="MintB", event_id="evt_a"),
        make_mixed_filter_input(token_mint="MintA", event_id="evt_a"),
        make_mixed_filter_input(token_mint="MintA", event_id="evt_b"),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    keys = tuple(
        (
            ev.filter_input.token_mint,
            ev.filter_input.event_id,
            ev.filter_input.captured_event_id,
            ev.filter_result.filter_name,
        )
        for ev in result.evaluations
    )
    assert keys == tuple(sorted(keys))


# ---------------------------------------------------------------------------
# Determinism: hash invariants
# ---------------------------------------------------------------------------


def test_same_inputs_same_timestamp_produce_same_evaluation_hashes():
    a = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    b = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    hashes_a = tuple(ev.evaluation_hash for ev in a.evaluations)
    hashes_b = tuple(ev.evaluation_hash for ev in b.evaluations)
    assert hashes_a == hashes_b


def test_same_inputs_same_timestamp_produce_same_input_hashes():
    a = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    b = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    input_hashes_a = tuple(ev.input_hash for ev in a.evaluations)
    input_hashes_b = tuple(ev.input_hash for ev in b.evaluations)
    assert input_hashes_a == input_hashes_b


def test_changed_input_changes_evaluation_hashes():
    base = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    different_input = make_mixed_filter_input(
        payload_summary=make_mixed_payload_summary(
            holder_overrides={"top_10_holder_pct": 0.95},
        ),
    )
    different = run_stage23_filters(
        filter_inputs=[different_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    base_hashes = sorted(ev.evaluation_hash for ev in base.evaluations)
    different_hashes = sorted(
        ev.evaluation_hash for ev in different.evaluations
    )
    assert base_hashes != different_hashes


def test_changed_timestamp_does_not_change_evaluation_hash():
    """``created_at_utc`` is NOT covered by the evaluation hash --
    the same logical evaluation at two different wall times must
    hash identically.
    """
    a = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc="2026-01-01T00:00:00Z",
    )
    b = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc="2026-06-15T18:30:00Z",
    )
    hashes_a = tuple(ev.evaluation_hash for ev in a.evaluations)
    hashes_b = tuple(ev.evaluation_hash for ev in b.evaluations)
    assert hashes_a == hashes_b


# ---------------------------------------------------------------------------
# Counter aggregation
# ---------------------------------------------------------------------------


def test_label_counts_total_matches_evaluation_count():
    inputs = [make_mixed_filter_input() for _ in range(5)]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    total = sum(result.label_counts.values())
    assert total == result.evaluation_count


def test_data_status_counts_total_matches_evaluation_count():
    inputs = [make_mixed_filter_input() for _ in range(5)]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    total = sum(result.data_status_counts.values())
    assert total == result.evaluation_count


def test_reason_code_counts_match_emitted_reasons():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    counted = dict(result.reason_code_counts)
    actual: dict[str, int] = {}
    for ev in result.evaluations:
        for code in ev.filter_result.reason_codes:
            actual[code] = actual.get(code, 0) + 1
    assert counted == actual


def test_label_counts_keys_are_closed_set():
    inputs = [
        make_mixed_filter_input(),
        make_filter_input(payload_summary=empty_payload_summary()),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for label in result.label_counts.keys():
        assert label in LABELS


def test_data_status_counts_keys_are_closed_set():
    inputs = [
        make_mixed_filter_input(),
        make_filter_input(payload_summary=empty_payload_summary()),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for status in result.data_status_counts.keys():
        assert status in DATA_STATUSES


# ---------------------------------------------------------------------------
# No input mutation
# ---------------------------------------------------------------------------


def test_runner_does_not_mutate_filter_input_payload_summary():
    payload = make_mixed_payload_summary()
    filter_input = make_mixed_filter_input(payload_summary=payload)
    snapshot_before = dict(filter_input.payload_summary)
    run_stage23_filters(
        filter_inputs=[filter_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    snapshot_after = dict(filter_input.payload_summary)
    assert snapshot_before == snapshot_after


def test_runner_does_not_replace_filter_input_object():
    filter_input = make_mixed_filter_input()
    result = run_stage23_filters(
        filter_inputs=[filter_input],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for ev in result.evaluations:
        assert ev.filter_input == filter_input


# ---------------------------------------------------------------------------
# Filter version / threshold version separation
# ---------------------------------------------------------------------------


def test_each_evaluation_carries_distinct_filter_version_per_filter():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    version_by_filter: dict[str, str] = {}
    for ev in result.evaluations:
        version_by_filter[ev.filter_result.filter_name] = (
            ev.filter_result.filter_version
        )
    assert version_by_filter == {
        "holder_concentration": "holder_concentration_v0",
        "launch_structure": "launch_structure_v0",
        "wallet_source_quality": "wallet_source_quality_v0",
    }


def test_each_evaluation_carries_threshold_version_independently_of_filter_version():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for ev in result.evaluations:
        r = ev.filter_result
        assert r.threshold_version == "thresholds_v0_observe_only"
        assert r.filter_version != r.threshold_version


# ---------------------------------------------------------------------------
# Closed-set output
# ---------------------------------------------------------------------------


def test_every_evaluation_label_is_closed_set():
    inputs = [
        make_mixed_filter_input(),
        make_filter_input(payload_summary=empty_payload_summary()),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for ev in result.evaluations:
        assert ev.filter_result.label in LABELS


def test_every_evaluation_data_status_is_closed_set():
    inputs = [
        make_mixed_filter_input(),
        make_filter_input(payload_summary=empty_payload_summary()),
    ]
    result = run_stage23_filters(
        filter_inputs=inputs,
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for ev in result.evaluations:
        assert ev.filter_result.data_status in DATA_STATUSES


def test_every_evaluation_filter_family_is_closed_set():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    for ev in result.evaluations:
        assert ev.filter_result.filter_family in FILTER_FAMILIES


# ---------------------------------------------------------------------------
# Empty inputs
# ---------------------------------------------------------------------------


def test_empty_input_list_produces_empty_evaluation_set():
    result = run_stage23_filters(
        filter_inputs=[],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert result.input_count == 0
    assert result.evaluation_count == 0
    assert result.filter_count == _DEFAULT_FILTER_COUNT
    assert result.evaluations == ()
    assert dict(result.label_counts) == {}
    assert dict(result.data_status_counts) == {}
    assert dict(result.reason_code_counts) == {}


# ---------------------------------------------------------------------------
# Typed Stage23Error handling
# ---------------------------------------------------------------------------


class _AlwaysRaisesStage23ErrorFilter:
    """Test double: a filter that always raises a typed Stage23Error.

    Used to exercise the runner's error-handling branch without
    relying on a real filter raising defensively.
    """

    filter_name: str = "always_raises_filter"
    filter_family: str = FILTER_FAMILY_HOLDER_CONCENTRATION
    filter_version: str = "always_raises_v0"
    threshold_version: str = "thresholds_v0_observe_only"

    def evaluate(
        self,
        *,
        filter_input: Stage23FilterInput,
    ) -> Stage23FilterResult:
        raise Stage23ContractError("test double always raises")


def test_runner_catches_typed_stage23_error_and_emits_unknown_record():
    runner_input = make_mixed_filter_input()
    result = run_stage23_filters(
        filter_inputs=[runner_input],
        created_at_utc=FIXED_CLOCK_UTC,
        filters=[_AlwaysRaisesStage23ErrorFilter()],
    )
    assert result.evaluation_count == 1
    ev = result.evaluations[0]
    assert ev.filter_result.label == LABEL_UNKNOWN
    assert ev.filter_result.data_status == DATA_STATUS_MISSING
    assert (
        REASON_STAGE23_FILTER_RAISED_ERROR
        in ev.filter_result.reason_codes
    )


def test_runner_error_record_preserves_filter_identity():
    runner_input = make_mixed_filter_input()
    result = run_stage23_filters(
        filter_inputs=[runner_input],
        created_at_utc=FIXED_CLOCK_UTC,
        filters=[_AlwaysRaisesStage23ErrorFilter()],
    )
    ev = result.evaluations[0]
    assert ev.filter_result.filter_name == "always_raises_filter"
    assert ev.filter_result.filter_version == "always_raises_v0"
    assert (
        ev.filter_result.threshold_version
        == "thresholds_v0_observe_only"
    )


class _RaisesRuntimeErrorFilter:
    """Test double: a filter that raises a non-Stage23 error.

    Untyped programmer errors must NOT be swallowed by the
    runner -- they propagate so the test surface notices.
    """

    filter_name: str = "always_raises_runtime"
    filter_family: str = FILTER_FAMILY_HOLDER_CONCENTRATION
    filter_version: str = "always_raises_runtime_v0"
    threshold_version: str = "thresholds_v0_observe_only"

    def evaluate(
        self,
        *,
        filter_input: Stage23FilterInput,
    ) -> Stage23FilterResult:
        raise RuntimeError("non-Stage23 error must propagate")


def test_runner_does_not_swallow_untyped_runtime_errors():
    with pytest.raises(RuntimeError):
        run_stage23_filters(
            filter_inputs=[make_mixed_filter_input()],
            created_at_utc=FIXED_CLOCK_UTC,
            filters=[_RaisesRuntimeErrorFilter()],
        )


def test_runner_reason_code_set_for_error_records_is_closed():
    assert STAGE23_RUNNER_REASON_CODES == (
        REASON_STAGE23_FILTER_RAISED_ERROR,
    )


# ---------------------------------------------------------------------------
# Created_at_utc validation
# ---------------------------------------------------------------------------


def test_empty_created_at_utc_is_rejected():
    with pytest.raises(Stage23ContractError):
        run_stage23_filters(
            filter_inputs=[make_mixed_filter_input()],
            created_at_utc="",
        )


def test_non_string_created_at_utc_is_rejected():
    with pytest.raises(Stage23ContractError):
        run_stage23_filters(
            filter_inputs=[make_mixed_filter_input()],
            created_at_utc=None,  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


def test_result_is_immutable_named_tuple():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
    )
    assert isinstance(result, Stage23RunnerResult)
    assert isinstance(result.evaluations, tuple)
    assert isinstance(result.label_counts, Mapping)
    assert isinstance(result.data_status_counts, Mapping)
    assert isinstance(result.reason_code_counts, Mapping)


def test_result_created_at_utc_round_trips_caller_value():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc="2026-03-04T05:06:07Z",
    )
    assert result.created_at_utc == "2026-03-04T05:06:07Z"
    for ev in result.evaluations:
        assert ev.created_at_utc == "2026-03-04T05:06:07Z"


def test_result_filter_count_matches_used_filter_set():
    custom = [
        HolderConcentrationFilter(),
        LaunchStructureFilter(),
    ]
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
        filters=custom,
    )
    assert result.filter_count == 2
    assert result.evaluation_count == 2


# ---------------------------------------------------------------------------
# Default-set wiring sanity
# ---------------------------------------------------------------------------


def test_default_filters_are_distinct_instances_per_call():
    """Each call to ``default_filters`` returns fresh instances so
    a runner cannot accidentally share state via module-level
    singletons.
    """
    a = default_filters()
    b = default_filters()
    for f_a, f_b in zip(a, b):
        assert f_a is not f_b


def test_runner_with_only_wallet_filter_yields_one_evaluation():
    result = run_stage23_filters(
        filter_inputs=[make_mixed_filter_input()],
        created_at_utc=FIXED_CLOCK_UTC,
        filters=[WalletSourceQualityFilter()],
    )
    assert result.filter_count == 1
    assert result.evaluation_count == 1
    assert (
        result.evaluations[0].filter_result.filter_name
        == "wallet_source_quality"
    )
