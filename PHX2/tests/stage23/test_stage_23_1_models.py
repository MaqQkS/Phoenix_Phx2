"""Stage 23.1 model tests.

Pins:

  * Immutability of Stage 23 NamedTuple records.
  * Required-field enforcement on the validated builders.
  * Deterministic canonical-JSON hashing (sorted keys, no
    whitespace separators, ASCII-safe).
  * Separation of ``filter_version`` and ``threshold_version``.
  * Reason codes are tuple-shaped and deterministic.
  * ``input_hash`` is stable under dict key reordering on the
    payload_summary.
  * ``evaluation_hash`` changes when label / reason / features
    change.
"""

from __future__ import annotations

from types import MappingProxyType

import pytest

from PHX2.stage23.constants import (
    DATA_STATUS_COMPLETE,
    FILTER_FAMILY_HOLDER_CONCENTRATION,
    LABEL_ELEVATED,
    LABEL_NORMAL,
)
from PHX2.stage23.errors import Stage23ContractError
from PHX2.stage23.models import (
    Stage23FilterEvaluation,
    Stage23FilterInput,
    Stage23FilterResult,
    build_filter_evaluation,
    build_filter_result,
    canonical_json,
    compute_evaluation_hash,
    compute_input_hash,
    stage23_hash,
)
from PHX2.tests.stage23.fixtures.builders import (
    FIXED_CLOCK_UTC,
    make_filter_input,
    make_filter_result,
)


# ---------------------------------------------------------------------------
# Immutability / NamedTuple structure
# ---------------------------------------------------------------------------


def test_stage23_filter_input_is_immutable():
    input_record = make_filter_input()
    with pytest.raises(AttributeError):
        input_record.token_mint = "different"  # type: ignore[misc]


def test_stage23_filter_result_is_immutable():
    result = make_filter_result()
    with pytest.raises(AttributeError):
        result.label = "different"  # type: ignore[misc]


def test_stage23_filter_evaluation_is_immutable():
    evaluation = build_filter_evaluation(
        filter_input=make_filter_input(),
        filter_result=make_filter_result(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    with pytest.raises(AttributeError):
        evaluation.created_at_utc = "different"  # type: ignore[misc]


def test_stage23_filter_input_is_a_namedtuple():
    assert issubclass(Stage23FilterInput, tuple)


def test_stage23_filter_result_is_a_namedtuple():
    assert issubclass(Stage23FilterResult, tuple)


def test_stage23_filter_evaluation_is_a_namedtuple():
    assert issubclass(Stage23FilterEvaluation, tuple)


# ---------------------------------------------------------------------------
# Required field enforcement
# ---------------------------------------------------------------------------


def test_build_filter_result_rejects_empty_filter_name():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="v1",
            threshold_version="v1",
            label=LABEL_NORMAL,
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_unknown_label():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="v1",
            threshold_version="v1",
            label="NOT_A_LOCKED_LABEL",
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_unknown_data_status():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="v1",
            threshold_version="v1",
            label=LABEL_NORMAL,
            data_status="NOT_A_LOCKED_STATUS",
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_unknown_filter_family():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family="NOT_A_FAMILY",
            filter_version="v1",
            threshold_version="v1",
            label=LABEL_NORMAL,
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_empty_filter_version():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="",
            threshold_version="v1",
            label=LABEL_NORMAL,
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_empty_threshold_version():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="v1",
            threshold_version="",
            label=LABEL_NORMAL,
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_non_tuple_reason_codes():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="v1",
            threshold_version="v1",
            label=LABEL_NORMAL,
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=["not", "a", "tuple"],  # type: ignore[arg-type]
            numeric_features=MappingProxyType({}),
            missing_features=(),
        )


def test_build_filter_result_rejects_non_tuple_missing_features():
    with pytest.raises(Stage23ContractError):
        build_filter_result(
            filter_name="x",
            filter_family=FILTER_FAMILY_HOLDER_CONCENTRATION,
            filter_version="v1",
            threshold_version="v1",
            label=LABEL_NORMAL,
            data_status=DATA_STATUS_COMPLETE,
            reason_codes=(),
            numeric_features=MappingProxyType({}),
            missing_features=["a", "b"],  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# filter_version and threshold_version separation
# ---------------------------------------------------------------------------


def test_filter_version_and_threshold_version_are_separate_fields():
    result = make_filter_result(
        filter_version="logic_v3",
        threshold_version="thresholds_v7",
    )
    assert result.filter_version == "logic_v3"
    assert result.threshold_version == "thresholds_v7"
    assert result.filter_version != result.threshold_version


def test_evaluation_hash_changes_when_only_threshold_version_changes():
    base_input = make_filter_input()
    a = make_filter_result(threshold_version="thresholds_v1")
    b = make_filter_result(threshold_version="thresholds_v2")
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


def test_evaluation_hash_changes_when_only_filter_version_changes():
    base_input = make_filter_input()
    a = make_filter_result(filter_version="logic_v1")
    b = make_filter_result(filter_version="logic_v2")
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


# ---------------------------------------------------------------------------
# reason_codes are tuple-like / deterministic
# ---------------------------------------------------------------------------


def test_reason_codes_are_stored_as_tuple():
    result = make_filter_result(reason_codes=("a", "b", "c"))
    assert isinstance(result.reason_codes, tuple)
    assert result.reason_codes == ("a", "b", "c")


def test_evaluation_hash_changes_when_reason_codes_change():
    base_input = make_filter_input()
    a = make_filter_result(reason_codes=("a",))
    b = make_filter_result(reason_codes=("b",))
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


def test_evaluation_hash_changes_when_reason_code_order_changes():
    base_input = make_filter_input()
    a = make_filter_result(reason_codes=("a", "b"))
    b = make_filter_result(reason_codes=("b", "a"))
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


# ---------------------------------------------------------------------------
# Hash determinism
# ---------------------------------------------------------------------------


def test_canonical_json_uses_sorted_keys_and_no_whitespace():
    encoded = canonical_json({"b": 1, "a": 2})
    assert encoded == '{"a":2,"b":1}'


def test_stage23_hash_is_64_char_lowercase_hex():
    digest = stage23_hash({"a": 1})
    assert len(digest) == 64
    assert digest == digest.lower()


def test_canonical_json_rejects_unsupported_type():
    with pytest.raises(Stage23ContractError):
        canonical_json(object())


def test_canonical_json_rejects_non_finite_float():
    with pytest.raises(Stage23ContractError):
        canonical_json(float("nan"))


# ---------------------------------------------------------------------------
# input_hash is deterministic across dict key ordering
# ---------------------------------------------------------------------------


def test_same_input_yields_same_input_hash():
    a = make_filter_input()
    b = make_filter_input()
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_is_stable_under_payload_summary_key_reorder():
    payload_a = MappingProxyType(
        {
            "alpha": 1,
            "beta": 2,
            "gamma": 3,
        }
    )
    # Same logical mapping with reversed insertion order.
    payload_b = MappingProxyType(
        {
            "gamma": 3,
            "beta": 2,
            "alpha": 1,
        }
    )
    a = make_filter_input(payload_summary=payload_a)
    b = make_filter_input(payload_summary=payload_b)
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_is_stable_when_payload_dict_has_different_iteration_order():
    payload_a: dict[str, object] = {}
    payload_a["x"] = 1
    payload_a["y"] = 2

    payload_b: dict[str, object] = {}
    payload_b["y"] = 2
    payload_b["x"] = 1

    a = make_filter_input(payload_summary=payload_a)
    b = make_filter_input(payload_summary=payload_b)
    assert compute_input_hash(a) == compute_input_hash(b)


def test_input_hash_changes_when_token_mint_changes():
    a = make_filter_input(token_mint="MintA")
    b = make_filter_input(token_mint="MintB")
    assert compute_input_hash(a) != compute_input_hash(b)


def test_input_hash_changes_when_missing_fields_differ():
    a = make_filter_input(missing_fields=())
    b = make_filter_input(missing_fields=("signature",))
    assert compute_input_hash(a) != compute_input_hash(b)


# ---------------------------------------------------------------------------
# evaluation_hash is deterministic and changes on relevant deltas
# ---------------------------------------------------------------------------


def test_same_evaluation_yields_same_evaluation_hash():
    a = compute_evaluation_hash(
        filter_input=make_filter_input(),
        filter_result=make_filter_result(),
    )
    b = compute_evaluation_hash(
        filter_input=make_filter_input(),
        filter_result=make_filter_result(),
    )
    assert a == b


def test_evaluation_hash_changes_when_label_changes():
    base_input = make_filter_input()
    a = make_filter_result(label=LABEL_NORMAL)
    b = make_filter_result(label=LABEL_ELEVATED)
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


def test_evaluation_hash_changes_when_numeric_features_change():
    base_input = make_filter_input()
    a = make_filter_result(
        numeric_features=MappingProxyType({"feature_a": 1.0})
    )
    b = make_filter_result(
        numeric_features=MappingProxyType({"feature_a": 2.0})
    )
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


def test_evaluation_hash_stable_under_numeric_features_key_reorder():
    base_input = make_filter_input()
    a = make_filter_result(
        numeric_features=MappingProxyType(
            {
                "alpha": 1.0,
                "beta": 2.0,
            }
        )
    )
    b = make_filter_result(
        numeric_features=MappingProxyType(
            {
                "beta": 2.0,
                "alpha": 1.0,
            }
        )
    )
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        == compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


def test_evaluation_hash_changes_when_missing_features_change():
    base_input = make_filter_input()
    a = make_filter_result(missing_features=())
    b = make_filter_result(missing_features=("feature_x",))
    assert (
        compute_evaluation_hash(
            filter_input=base_input,
            filter_result=a,
        )
        != compute_evaluation_hash(
            filter_input=base_input,
            filter_result=b,
        )
    )


# ---------------------------------------------------------------------------
# build_filter_evaluation: created_at_utc is NOT in hashes
# ---------------------------------------------------------------------------


def test_build_filter_evaluation_omits_created_at_from_hashes():
    a = build_filter_evaluation(
        filter_input=make_filter_input(),
        filter_result=make_filter_result(),
        created_at_utc="2026-01-01T00:00:00Z",
    )
    b = build_filter_evaluation(
        filter_input=make_filter_input(),
        filter_result=make_filter_result(),
        created_at_utc="2027-09-09T12:34:56Z",
    )
    assert a.input_hash == b.input_hash
    assert a.evaluation_hash == b.evaluation_hash
    assert a.created_at_utc != b.created_at_utc


def test_build_filter_evaluation_rejects_empty_created_at():
    with pytest.raises(Stage23ContractError):
        build_filter_evaluation(
            filter_input=make_filter_input(),
            filter_result=make_filter_result(),
            created_at_utc="",
        )


def test_build_filter_evaluation_carries_consistent_hashes():
    evaluation = build_filter_evaluation(
        filter_input=make_filter_input(),
        filter_result=make_filter_result(),
        created_at_utc=FIXED_CLOCK_UTC,
    )
    expected_input_hash = compute_input_hash(evaluation.filter_input)
    expected_evaluation_hash = compute_evaluation_hash(
        filter_input=evaluation.filter_input,
        filter_result=evaluation.filter_result,
    )
    assert evaluation.input_hash == expected_input_hash
    assert evaluation.evaluation_hash == expected_evaluation_hash
