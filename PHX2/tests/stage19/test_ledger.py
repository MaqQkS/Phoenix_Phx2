"""Stage 19 ledger tests.

Covers:
  * LedgerRow / SummaryRow shape (anchored to LEDGER_COLUMNS /
    SUMMARY_COLUMNS via the Phase 19.1 test_constants.py).
  * build_ledger_rows -- review_sequence chain, ledger_row_id
    determinism, classification mapping, timestamp passthrough,
    canonical sort order.
  * merge_ledger -- canonical sort, prior-row preservation.
  * compute_summary -- MAX(review_sequence) selection per
    (slice, operator), canonical sort.
"""

from __future__ import annotations

import pytest

from PHX2.stage19 import ledger
from PHX2.stage19.constants import LEDGER_COLUMNS, SUMMARY_COLUMNS
from PHX2.stage19.ledger import LedgerRow, SummaryRow
from PHX2.stage19.readers import OperatorInputRow, ReviewMatrixRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DEFAULT_RUN_ID = "0123456789abcdef"
_DEFAULT_POLICY = "abc123def456"
_DEFAULT_RULE = "rule_minimal"
_DEFAULT_WINDOW = 3600
_DEFAULT_TS = "2026-05-14T05:00:00Z"


def _op_row(
    *,
    stage18_run_id: str = _DEFAULT_RUN_ID,
    policy_hash: str = _DEFAULT_POLICY,
    rule_id: str = _DEFAULT_RULE,
    window_seconds: int = _DEFAULT_WINDOW,
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "ok",
) -> OperatorInputRow:
    return OperatorInputRow(
        stage18_run_id=stage18_run_id,
        policy_hash=policy_hash,
        rule_id=rule_id,
        window_seconds=window_seconds,
        review_label=review_label,
        review_notes=review_notes,
    )


def _matrix_index(
    keys: list[tuple[str, str, int]] | None = None,
    *,
    classification: str = "PROMISING_REVIEW",
    stage17: str = "PROMISING",
) -> dict[tuple[str, str, int], ReviewMatrixRecord]:
    if keys is None:
        keys = [(_DEFAULT_POLICY, _DEFAULT_RULE, _DEFAULT_WINDOW)]
    return {
        k: ReviewMatrixRecord(
            policy_hash=k[0],
            rule_id=k[1],
            window_seconds=k[2],
            stage18_classification=classification,
            stage17_label_preserved=stage17,
        )
        for k in keys
    }


def _existing_ledger_row(
    *,
    stage18_run_id: str = _DEFAULT_RUN_ID,
    policy_hash: str = _DEFAULT_POLICY,
    rule_id: str = _DEFAULT_RULE,
    window_seconds: int = _DEFAULT_WINDOW,
    operator_id: str = "alice",
    review_sequence: int = 1,
    stage19_run_id: str = "stage19_prior",
    ledger_row_id: str = "00000000deadbeef",
    review_label: str = "REVIEW_PROMISING_CONFIRMED",
    review_notes: str = "prior note",
    review_timestamp_utc: str = "2026-05-13T12:00:00Z",
    stage18_classification: str = "PROMISING_REVIEW",
    stage17_label_preserved: str = "PROMISING",
) -> LedgerRow:
    return LedgerRow(
        stage19_run_id=stage19_run_id,
        ledger_row_id=ledger_row_id,
        stage18_run_id=stage18_run_id,
        policy_hash=policy_hash,
        rule_id=rule_id,
        window_seconds=window_seconds,
        operator_id=operator_id,
        review_sequence=review_sequence,
        review_label=review_label,
        review_notes=review_notes,
        review_timestamp_utc=review_timestamp_utc,
        stage18_classification=stage18_classification,
        stage17_label_preserved=stage17_label_preserved,
    )


# ===========================================================================
# LedgerRow / SummaryRow shape
# ===========================================================================


class TestLedgerRowShape:
    def test_field_count_matches_ledger_columns(self) -> None:
        assert len(LedgerRow._fields) == len(LEDGER_COLUMNS)

    def test_field_order_matches_ledger_columns(self) -> None:
        assert LedgerRow._fields == LEDGER_COLUMNS


class TestSummaryRowShape:
    def test_field_count_matches_summary_columns(self) -> None:
        assert len(SummaryRow._fields) == len(SUMMARY_COLUMNS)

    def test_field_order_matches_summary_columns(self) -> None:
        assert SummaryRow._fields == SUMMARY_COLUMNS


# ===========================================================================
# build_ledger_rows
# ===========================================================================


class TestBuildLedgerRowsSequence:
    def test_first_review_with_empty_prior_gets_sequence_1(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_aaa",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert len(out) == 1
        assert out[0].review_sequence == 1

    def test_second_review_with_prior_seq_1_gets_sequence_2(self) -> None:
        prior = [_existing_ledger_row(operator_id="alice", review_sequence=1)]
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=prior,
            stage19_run_id="run_bbb",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert out[0].review_sequence == 2

    def test_third_review_with_prior_max_2_gets_sequence_3(self) -> None:
        prior = [
            _existing_ledger_row(operator_id="alice", review_sequence=1),
            _existing_ledger_row(operator_id="alice", review_sequence=2),
        ]
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=prior,
            stage19_run_id="run_ccc",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert out[0].review_sequence == 3

    def test_two_operators_each_get_sequence_1_for_same_identity(self) -> None:
        # First, alice reviews
        out_a = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        # Then bob reviews — alice's prior row is in the merged ledger
        bob_out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=out_a,
            stage19_run_id="run_b",
            operator_id="bob",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert out_a[0].review_sequence == 1
        assert bob_out[0].review_sequence == 1  # Independent chain per operator

    def test_alice_revisits_after_bob_still_increments_alice_chain(self) -> None:
        # Prior: alice seq 1, bob seq 1
        prior = [
            _existing_ledger_row(operator_id="alice", review_sequence=1),
            _existing_ledger_row(operator_id="bob", review_sequence=1),
        ]
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=prior,
            stage19_run_id="run_2",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert out[0].review_sequence == 2  # alice's chain continues

    def test_two_new_rows_same_slice_same_operator_get_sequential_numbers(
        self,
    ) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row(), _op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_x",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert sorted(r.review_sequence for r in out) == [1, 2]


class TestBuildLedgerRowsRowId:
    def test_ledger_row_id_deterministic_for_identical_inputs(self) -> None:
        kwargs = dict(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_aaa",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        out1 = ledger.build_ledger_rows(**kwargs)
        out2 = ledger.build_ledger_rows(**kwargs)
        assert out1[0].ledger_row_id == out2[0].ledger_row_id

    def test_ledger_row_id_changes_when_stage19_run_id_changes(self) -> None:
        a = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        b = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_b",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert a[0].ledger_row_id != b[0].ledger_row_id

    def test_ledger_row_id_changes_when_operator_id_changes(self) -> None:
        a = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_x",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        b = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_x",
            operator_id="bob",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert a[0].ledger_row_id != b[0].ledger_row_id

    def test_ledger_row_id_changes_when_review_sequence_changes(self) -> None:
        a = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_x",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        # Force review_sequence=2 by giving prior row at seq 1
        prior = [_existing_ledger_row(operator_id="alice", review_sequence=1)]
        b = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=prior,
            stage19_run_id="run_x",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert a[0].ledger_row_id != b[0].ledger_row_id

    def test_ledger_row_id_is_16_lowercase_hex_chars(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        rid = out[0].ledger_row_id
        assert len(rid) == 16
        assert rid == rid.lower()
        assert all(c in "0123456789abcdef" for c in rid)


class TestBuildLedgerRowsMapping:
    def test_stage18_classification_sourced_from_review_matrix(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(
                classification="HARMFUL_REVIEW", stage17="HARMFUL"
            ),
        )
        assert out[0].stage18_classification == "HARMFUL_REVIEW"

    def test_stage17_label_passthrough(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row()],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(
                classification="WEAK_REVIEW", stage17="WEAK"
            ),
        )
        assert out[0].stage17_label_preserved == "WEAK"

    def test_review_timestamp_utc_matches_argument(self) -> None:
        ts = "2026-12-31T23:59:59Z"
        out = ledger.build_ledger_rows(
            operator_input=[_op_row(), _op_row(rule_id="rule_other")],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=ts,
            review_matrix_index=_matrix_index([
                (_DEFAULT_POLICY, _DEFAULT_RULE, _DEFAULT_WINDOW),
                (_DEFAULT_POLICY, "rule_other", _DEFAULT_WINDOW),
            ]),
        )
        for row in out:
            assert row.review_timestamp_utc == ts

    def test_operator_id_set_on_every_row(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row(), _op_row(rule_id="rule_b")],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="charlie",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index([
                (_DEFAULT_POLICY, _DEFAULT_RULE, _DEFAULT_WINDOW),
                (_DEFAULT_POLICY, "rule_b", _DEFAULT_WINDOW),
            ]),
        )
        assert all(r.operator_id == "charlie" for r in out)

    def test_review_label_passthrough_from_input(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[_op_row(review_label="WATCHLIST")],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index(),
        )
        assert out[0].review_label == "WATCHLIST"


class TestBuildLedgerRowsSort:
    def test_output_sorted_by_canonical_d3_order(self) -> None:
        out = ledger.build_ledger_rows(
            operator_input=[
                _op_row(rule_id="z_rule"),
                _op_row(rule_id="a_rule"),
                _op_row(rule_id="m_rule"),
            ],
            prior_ledger_rows=[],
            stage19_run_id="run_a",
            operator_id="alice",
            review_timestamp_utc=_DEFAULT_TS,
            review_matrix_index=_matrix_index([
                (_DEFAULT_POLICY, "a_rule", _DEFAULT_WINDOW),
                (_DEFAULT_POLICY, "m_rule", _DEFAULT_WINDOW),
                (_DEFAULT_POLICY, "z_rule", _DEFAULT_WINDOW),
            ]),
        )
        assert [r.rule_id for r in out] == ["a_rule", "m_rule", "z_rule"]


# ===========================================================================
# merge_ledger
# ===========================================================================


class TestMergeLedger:
    def test_empty_prior_plus_three_new_returns_three_sorted(self) -> None:
        new_rows = [
            _existing_ledger_row(rule_id="z", review_sequence=1),
            _existing_ledger_row(rule_id="a", review_sequence=1),
            _existing_ledger_row(rule_id="m", review_sequence=1),
        ]
        out = ledger.merge_ledger([], new_rows)
        assert [r.rule_id for r in out] == ["a", "m", "z"]

    def test_two_prior_plus_three_new_returns_five_sorted(self) -> None:
        prior = [
            _existing_ledger_row(rule_id="b", review_sequence=1),
            _existing_ledger_row(rule_id="d", review_sequence=1),
        ]
        new_rows = [
            _existing_ledger_row(rule_id="a", review_sequence=2),
            _existing_ledger_row(rule_id="c", review_sequence=1),
            _existing_ledger_row(rule_id="e", review_sequence=1),
        ]
        out = ledger.merge_ledger(prior, new_rows)
        assert len(out) == 5
        assert [r.rule_id for r in out] == ["a", "b", "c", "d", "e"]

    def test_prior_rows_preserved_field_for_field(self) -> None:
        prior = [
            _existing_ledger_row(
                rule_id="x",
                review_sequence=7,
                ledger_row_id="aaaaaaaaaaaaaaaa",
                review_notes="prior note",
                review_timestamp_utc="2025-01-01T00:00:00Z",
            )
        ]
        new_rows = [
            _existing_ledger_row(
                rule_id="y",
                review_sequence=1,
                ledger_row_id="bbbbbbbbbbbbbbbb",
            )
        ]
        out = ledger.merge_ledger(prior, new_rows)
        # Find the prior row in output and verify all fields preserved
        prior_row = next(r for r in out if r.rule_id == "x")
        assert prior_row == prior[0]

    def test_canonical_sort_uses_int_window_seconds_not_string(self) -> None:
        # Build rows with window_seconds 60, 600, 3600. Lexicographic
        # string sort would put "3600" before "600" before "60";
        # numeric sort yields 60, 600, 3600.
        rows = [
            _existing_ledger_row(window_seconds=600),
            _existing_ledger_row(window_seconds=60),
            _existing_ledger_row(window_seconds=3600),
        ]
        out = ledger.merge_ledger([], rows)
        assert [r.window_seconds for r in out] == [60, 600, 3600]


# ===========================================================================
# compute_summary
# ===========================================================================


class TestComputeSummary:
    def test_three_reviews_same_identity_operator_one_summary_at_seq_3(
        self,
    ) -> None:
        rows = [
            _existing_ledger_row(operator_id="alice", review_sequence=1),
            _existing_ledger_row(operator_id="alice", review_sequence=2),
            _existing_ledger_row(
                operator_id="alice",
                review_sequence=3,
                review_label="WATCHLIST",
            ),
        ]
        out = ledger.compute_summary(rows)
        assert len(out) == 1
        assert out[0].current_review_sequence == 3
        assert out[0].current_review_label == "WATCHLIST"

    def test_two_operators_one_review_each_two_summary_rows(self) -> None:
        rows = [
            _existing_ledger_row(operator_id="alice", review_sequence=1),
            _existing_ledger_row(operator_id="bob", review_sequence=1),
        ]
        out = ledger.compute_summary(rows)
        assert len(out) == 2
        assert {r.operator_id for r in out} == {"alice", "bob"}

    def test_empty_ledger_yields_empty_summary(self) -> None:
        assert ledger.compute_summary([]) == []

    def test_summary_fields_pulled_from_max_sequence_row(self) -> None:
        rows = [
            _existing_ledger_row(
                operator_id="alice",
                review_sequence=1,
                review_label="REVIEW_PROMISING_CONFIRMED",
                review_notes="initial",
                review_timestamp_utc="2026-05-13T00:00:00Z",
            ),
            _existing_ledger_row(
                operator_id="alice",
                review_sequence=2,
                review_label="WATCHLIST",
                review_notes="changed mind",
                review_timestamp_utc="2026-05-14T00:00:00Z",
            ),
        ]
        out = ledger.compute_summary(rows)
        assert len(out) == 1
        assert out[0].current_review_sequence == 2
        assert out[0].current_review_label == "WATCHLIST"
        assert out[0].current_review_notes == "changed mind"
        assert out[0].current_review_timestamp_utc == "2026-05-14T00:00:00Z"

    def test_summary_sorted_by_canonical_d4_order(self) -> None:
        rows = [
            _existing_ledger_row(rule_id="z_rule", operator_id="alice"),
            _existing_ledger_row(rule_id="a_rule", operator_id="alice"),
            _existing_ledger_row(rule_id="m_rule", operator_id="alice"),
        ]
        out = ledger.compute_summary(rows)
        assert [r.rule_id for r in out] == ["a_rule", "m_rule", "z_rule"]

    def test_summary_includes_stage18_evidence_passthrough(self) -> None:
        rows = [
            _existing_ledger_row(
                operator_id="alice",
                review_sequence=1,
                stage18_classification="HARMFUL_REVIEW",
                stage17_label_preserved="HARMFUL",
            ),
        ]
        out = ledger.compute_summary(rows)
        assert out[0].stage18_classification == "HARMFUL_REVIEW"
        assert out[0].stage17_label_preserved == "HARMFUL"
