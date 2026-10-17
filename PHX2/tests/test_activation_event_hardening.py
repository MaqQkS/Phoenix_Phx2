"""Activation-event torn-write hardening + per-line scanner tolerance (2026-07-29 Gate G).

The failed short-acceptance gate proved one defect chain:

    concurrent/interrupted JSONL append -> torn ``activation_events.jsonl``
    line -> whole-file structured masking abandoned -> allowlisted fixed
    public enum reaches the raw needle scan -> false REDACTION_VIOLATION ->
    SECRET_SCAN_FAILURE -> producer exit -> watchdog restart.

These tests pin BOTH remediations:

  * ``serialized_jsonl.SerializedJsonlAppender`` — serialize-first,
    lock-serialized, single-``os.write`` append; no interleaving, no silent
    loss, append-only, failures raised with closed-set tokens.
  * ``production_live_artifacts`` per-line JSONL masking — one malformed line
    is disclosed (line number / error class / truncated-vs-malformed status)
    and scanned RAW, while every valid neighboring line keeps its structured
    enum masking; genuine needles anywhere stay immediately UNSAFE.

Needle-bearing strings below are assembled from pieces so THIS source file
never carries a raw danger needle (same convention as the scanner's own
positive control).
"""

from __future__ import annotations

import json
import os
import threading

import pytest

from PHX2.free_tier_producer import serialized_jsonl
from PHX2.free_tier_producer.serialized_jsonl import (
    APPEND_FAILED_OS_ERROR,
    APPEND_REFUSED_CLOSED,
    APPEND_REFUSED_FORBIDDEN_BYTE,
    APPEND_REFUSED_NOT_SERIALIZABLE,
    SerializedJsonlAppendError,
    SerializedJsonlAppender,
)
from PHX2.free_tier_producer.compat import production_live_artifacts as pla
from PHX2.free_tier_producer.compat.production_live_runner import (
    SCAN_VERDICT_CLEAN,
    SCAN_VERDICT_UNSAFE,
    ScanFailureDebounce,
    classify_redaction_scan,
)

# The exact allowlisted fixed public enum that reached the raw scan in the
# preserved failed runs (assembled so this source carries no needle piece).
ALLOWLISTED_ENUM = "DEX" + "SCREENER_SOL_USD_X_410_INFERRED"
# A same-family value that is NOT in the fixed allowlist (must stay flagged).
NON_ALLOWLISTED_ENUM = "DEX" + "SCREENER_SOMETHING_ELSE"
# Genuine danger needles, assembled in pieces (no piece is itself a needle).
SECRET_ENDPOINT = "wss" + ":" + "//example-endpoint/?api-" + "key=PLANTEDVALUE"
SECRET_HEADER_FRAGMENT = "api" + "-key=PLANTED"


def _valid_activation_record(seq: int, *, enum_status: str | None = None):
    record = {
        "kind": "PHX2_WATCHLIST_EVENT",
        "event": "BASELINE_CAPTURED",
        "token_mint": f"MintFixture{seq:05d}",
        "sequence": seq,
        "baseline_market_cap_usd": 41000.5 + seq,
        "observed_at_utc": "2026-07-29T01:00:00Z",
    }
    if enum_status is not None:
        record["price_status"] = enum_status
    return record


def _read_lines(path):
    data = path.read_bytes()
    assert data.endswith(b"\n"), "file must end at a record boundary"
    return data.decode("utf-8").splitlines()


# ---------------------------------------------------------------------------
# Serialized appender: correctness of one append
# ---------------------------------------------------------------------------


def test_single_valid_append_parses_and_ends_at_boundary(tmp_path):
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    try:
        appender.append(_valid_activation_record(1))
    finally:
        appender.close()
    lines = _read_lines(path)
    assert len(lines) == 1
    assert json.loads(lines[0])["sequence"] == 1
    assert appender.appended_records == 1
    assert appender.failed_appends == 0


def test_record_serialization_byte_parity_with_legacy(tmp_path):
    """The on-disk record shape is EXACTLY the legacy ``_append_jsonl`` bytes."""

    record = _valid_activation_record(7, enum_status=ALLOWLISTED_ENUM)
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    try:
        appender.append(record)
    finally:
        appender.close()
    legacy_line = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    assert path.read_bytes() == legacy_line


def test_appends_are_append_only_prefix_preserved(tmp_path):
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    try:
        for seq in range(3):
            appender.append(_valid_activation_record(seq))
        prefix = path.read_bytes()
        appender.append(_valid_activation_record(99))
    finally:
        appender.close()
    final = path.read_bytes()
    assert final.startswith(prefix), "existing records must never be rewritten"
    assert len(_read_lines(path)) == 4


# ---------------------------------------------------------------------------
# Serialized appender: concurrency
# ---------------------------------------------------------------------------


def _run_concurrent_writers(path, *, writers: int, records_each: int,
                            fsync_records: bool):
    appender = SerializedJsonlAppender(path, fsync_records=fsync_records)
    barrier = threading.Barrier(writers)
    errors: list = []

    def work(writer_id: int) -> None:
        barrier.wait()
        for seq in range(records_each):
            record = _valid_activation_record(seq)
            record["writer_id"] = writer_id
            # Varied payload size stresses differing write lengths (the
            # preserved tears involved unequal racing record lengths).
            record["padding"] = "x" * ((writer_id * 37 + seq * 13) % 900)
            try:
                appender.append(record)
            except Exception as exc:  # pragma: no cover - failure evidence
                errors.append(exc)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(writers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    appender.close()
    assert not errors, f"concurrent appends raised: {errors[:3]}"
    return appender


def test_two_concurrent_appends_both_complete(tmp_path):
    path = tmp_path / "activation_events.jsonl"
    _run_concurrent_writers(path, writers=2, records_each=1,
                            fsync_records=True)
    lines = _read_lines(path)
    assert len(lines) == 2
    assert {json.loads(line)["writer_id"] for line in lines} == {0, 1}


def test_many_concurrent_appends_no_interleave_exact_counts(tmp_path):
    """Deterministic verification (not timing): every line parses alone, no
    fused/interleaved objects, and every (writer, sequence) id is recovered
    exactly once — enough volume to expose interleaving if locking is absent."""

    writers, records_each = 8, 200
    path = tmp_path / "activation_events.jsonl"
    appender = _run_concurrent_writers(
        path, writers=writers, records_each=records_each, fsync_records=False)
    lines = _read_lines(path)
    assert len(lines) == writers * records_each
    assert appender.appended_records == writers * records_each
    seen = set()
    for line in lines:
        assert line.count("}{") == 0, "two records fused on one line"
        parsed = json.loads(line)  # raises -> torn/interleaved record
        seen.add((parsed["writer_id"], parsed["sequence"]))
    expected = {(w, s) for w in range(writers) for s in range(records_each)}
    assert seen == expected, "record ids/counts must match exactly"


def test_concurrent_appends_with_fsync_default_path(tmp_path):
    path = tmp_path / "activation_events.jsonl"
    _run_concurrent_writers(path, writers=2, records_each=25,
                            fsync_records=True)
    lines = _read_lines(path)
    assert len(lines) == 50
    assert all(json.loads(line) for line in lines)


# ---------------------------------------------------------------------------
# Serialized appender: failure handling (no silent loss, no truncation)
# ---------------------------------------------------------------------------


def test_preparation_failure_before_append_writes_nothing(tmp_path):
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    try:
        with pytest.raises(SerializedJsonlAppendError) as excinfo:
            appender.append({"unserializable": {1, 2, 3}})
        assert excinfo.value.reason == APPEND_REFUSED_NOT_SERIALIZABLE
        assert not path.exists(), "preparation failure must not touch the file"
        appender.append(_valid_activation_record(1))
    finally:
        appender.close()
    assert len(_read_lines(path)) == 1
    assert appender.failed_appends == 1
    assert appender.appended_records == 1


def test_forbidden_byte_payload_is_refused_before_open(tmp_path, monkeypatch):
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    monkeypatch.setattr(serialized_jsonl.json, "dumps",
                        lambda *a, **k: '{"broken": "one\nline"}')
    try:
        with pytest.raises(SerializedJsonlAppendError) as excinfo:
            appender.append(_valid_activation_record(1))
    finally:
        appender.close()
    assert excinfo.value.reason == APPEND_REFUSED_FORBIDDEN_BYTE
    assert not path.exists()


def test_os_write_failure_raises_and_earlier_records_survive(tmp_path, monkeypatch):
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    real_write = os.write
    try:
        appender.append(_valid_activation_record(1))
        prefix = path.read_bytes()
        target_fd = appender._fd
        arm = {"fail": True}

        def failing_write(fd, data):
            if fd == target_fd and arm["fail"]:
                arm["fail"] = False
                raise OSError(28, "simulated append failure")
            return real_write(fd, data)

        monkeypatch.setattr(os, "write", failing_write)
        with pytest.raises(SerializedJsonlAppendError) as excinfo:
            appender.append(_valid_activation_record(2))
        assert excinfo.value.reason == APPEND_FAILED_OS_ERROR
        assert excinfo.value.error_type == "OSError"
        assert path.read_bytes() == prefix, "failure must not truncate history"
        appender.append(_valid_activation_record(3))
    finally:
        monkeypatch.setattr(os, "write", real_write)
        appender.close()
    lines = _read_lines(path)
    assert [json.loads(l)["sequence"] for l in lines] == [1, 3]
    assert appender.failed_appends == 1


def test_interrupted_half_write_leaves_torn_tail_but_history_intact(
        tmp_path, monkeypatch):
    """Simulated crash mid-record: earlier records stay intact and the torn
    tail is exactly the artifact class the per-line scanner now tolerates."""

    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    real_write = os.write
    try:
        appender.append(_valid_activation_record(1))
        prefix = path.read_bytes()
        target_fd = appender._fd
        arm = {"tear": True}

        def torn_write(fd, data):
            if fd == target_fd and arm["tear"]:
                arm["tear"] = False
                real_write(fd, data[: max(1, len(data) // 2)])
                raise OSError(28, "simulated interruption mid-record")
            return real_write(fd, data)

        monkeypatch.setattr(os, "write", torn_write)
        with pytest.raises(SerializedJsonlAppendError):
            appender.append(_valid_activation_record(2))
    finally:
        monkeypatch.setattr(os, "write", real_write)
        appender.close()
    data = path.read_bytes()
    assert data.startswith(prefix), "interruption must not damage history"
    assert not data.endswith(b"\n"), "simulated crash leaves a torn tail"
    first_line = data.decode("utf-8").split("\n")[0]
    assert json.loads(first_line)["sequence"] == 1


def test_closed_appender_refuses_disclosed(tmp_path):
    path = tmp_path / "activation_events.jsonl"
    appender = SerializedJsonlAppender(path)
    appender.append(_valid_activation_record(1))
    appender.close()
    with pytest.raises(SerializedJsonlAppendError) as excinfo:
        appender.append(_valid_activation_record(2))
    assert excinfo.value.reason == APPEND_REFUSED_CLOSED
    assert len(_read_lines(path)) == 1


def test_append_error_tokens_are_scan_safe():
    """The disclosure path (errors.jsonl note) must never self-trip the scanner."""

    for reason in (APPEND_FAILED_OS_ERROR, APPEND_REFUSED_CLOSED,
                   APPEND_REFUSED_FORBIDDEN_BYTE,
                   APPEND_REFUSED_NOT_SERIALIZABLE):
        note = f"{reason}:OSError"
        assert pla.scan_value_safe(note), note


# ---------------------------------------------------------------------------
# Scanner: per-line JSONL tolerance
# ---------------------------------------------------------------------------


def _write_activation_fixture(tmp_path, *, torn_line_at: str,
                              torn_content: str = '4123.5,"tier":"T2"}'):
    """A synthetic activation_events.jsonl mirroring the preserved failed runs:
    valid records carrying the allowlisted enum, plus ONE torn tail-fragment
    line (front of the record destroyed, tail left behind)."""

    assert ALLOWLISTED_ENUM in pla.FIXED_PUBLIC_REDACTION_TOKENS
    valid = [
        json.dumps(_valid_activation_record(seq, enum_status=ALLOWLISTED_ENUM),
                   sort_keys=True)
        for seq in range(4)
    ]
    if torn_line_at == "middle":
        lines = valid[:2] + [torn_content] + valid[2:]
        payload = "\n".join(lines) + "\n"
        torn_line_number = 3
    elif torn_line_at == "final":
        lines = valid + [torn_content]
        payload = "\n".join(lines)  # no trailing newline: truncated tail
        torn_line_number = 5
    else:  # pragma: no cover - fixture misuse
        raise AssertionError(torn_line_at)
    path = tmp_path / "activation_events.jsonl"
    path.write_text(payload, encoding="utf-8", newline="")
    return path, torn_line_number


def test_malformed_middle_line_disclosed_and_neighbors_masked(tmp_path):
    _, torn_line_number = _write_activation_fixture(
        tmp_path, torn_line_at="middle")
    scan = pla.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTED"
    assert scan["total_unsafe_hits"] == 0
    assert scan["per_file_hits"]["activation_events.jsonl"] == []
    report = scan["malformed_jsonl_lines"]["activation_events.jsonl"]
    assert report["total"] == 1 and report["listed"] == 1
    (entry,) = report["lines"]
    assert entry["line_number"] == torn_line_number
    assert entry["error_class"] == "JSONDecodeError"
    assert entry["status"] == pla.MALFORMED_LINE_STATUS
    assert scan["malformed_jsonl_line_total"] == 1
    assert scan["positive_control_ok"] is True


def test_torn_final_line_disclosed_as_truncated(tmp_path):
    _, torn_line_number = _write_activation_fixture(
        tmp_path, torn_line_at="final")
    scan = pla.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTED"
    (entry,) = scan["malformed_jsonl_lines"]["activation_events.jsonl"]["lines"]
    assert entry["line_number"] == torn_line_number
    assert entry["status"] == pla.TRUNCATED_FINAL_LINE_STATUS


def test_reproduced_failed_run_pattern_no_false_stop(tmp_path):
    """The exact run-1/run-2 pattern must classify CLEAN: no stop, no
    SECRET_SCAN_FAILURE — while the torn line stays disclosed."""

    _write_activation_fixture(tmp_path, torn_line_at="middle")
    scan = pla.run_redaction_scan(tmp_path)
    verdict = classify_redaction_scan(scan)
    assert verdict == SCAN_VERDICT_CLEAN
    assert ScanFailureDebounce().observe(verdict) is False
    assert scan["malformed_jsonl_line_total"] == 1


def test_real_secret_in_valid_line_immediate_unsafe(tmp_path):
    record = _valid_activation_record(1, enum_status=ALLOWLISTED_ENUM)
    record["leaked"] = SECRET_ENDPOINT
    path = tmp_path / "activation_events.jsonl"
    path.write_text(json.dumps(record, sort_keys=True) + "\n",
                    encoding="utf-8", newline="")
    scan = pla.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTION_VIOLATION"
    assert scan["total_unsafe_hits"] > 0
    assert classify_redaction_scan(scan) == SCAN_VERDICT_UNSAFE
    assert ScanFailureDebounce().observe(SCAN_VERDICT_UNSAFE) is True


def test_real_secret_in_malformed_line_immediate_unsafe(tmp_path):
    _write_activation_fixture(
        tmp_path, torn_line_at="middle",
        torn_content='4123.5,"leak":"' + SECRET_HEADER_FRAGMENT + '"}')
    scan = pla.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTION_VIOLATION"
    assert scan["total_unsafe_hits"] > 0
    assert classify_redaction_scan(scan) == SCAN_VERDICT_UNSAFE
    # The torn line is still disclosed alongside the genuine hit.
    assert scan["malformed_jsonl_line_total"] == 1


def test_malformed_line_never_unmasks_other_files_or_lines():
    """Direct unit check of the per-line masking contract."""

    valid_enum_line = json.dumps(
        _valid_activation_record(0, enum_status=ALLOWLISTED_ENUM),
        sort_keys=True)
    torn = '4123.5,"tier":"T2"}'
    hits, malformed = pla.scan_text_with_jsonl_report(
        valid_enum_line + "\n" + torn + "\n" + valid_enum_line + "\n")
    assert hits == []
    assert [entry["line_number"] for entry in malformed] == [2]


def test_non_allowlisted_same_family_value_still_flagged():
    """Masking is equality-only: unknown same-family values keep failing closed
    (detection is NOT weakened by the per-line change)."""

    assert NON_ALLOWLISTED_ENUM not in pla.FIXED_PUBLIC_REDACTION_TOKENS
    record = _valid_activation_record(0, enum_status=NON_ALLOWLISTED_ENUM)
    hits, malformed = pla.scan_text_with_jsonl_report(
        json.dumps(record, sort_keys=True) + "\n")
    assert hits, "unknown same-family value must remain a needle hit"
    assert malformed == []


def test_plain_text_file_behavior_unchanged(tmp_path):
    (tmp_path / "console.log").write_text(
        "producer starting\nstream connected\nno json here\n",
        encoding="utf-8")
    scan = pla.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTED"
    assert scan["malformed_jsonl_lines"] == {}
    assert scan["malformed_jsonl_line_total"] == 0


def test_plain_text_file_with_secret_still_unsafe(tmp_path):
    (tmp_path / "console.log").write_text(
        "connecting to " + SECRET_ENDPOINT + "\n", encoding="utf-8")
    scan = pla.run_redaction_scan(tmp_path)
    assert scan["redaction_status"] == "REDACTION_VIOLATION"


def test_whole_doc_json_masking_unchanged():
    doc = json.dumps({"price_status": ALLOWLISTED_ENUM}, sort_keys=True)
    hits, malformed = pla.scan_text_with_jsonl_report(doc)
    assert hits == []
    assert malformed == []


def test_malformed_report_listing_is_capped_but_total_exact(tmp_path):
    valid = json.dumps(
        _valid_activation_record(0, enum_status=ALLOWLISTED_ENUM),
        sort_keys=True)
    torn_lines = ['%d,"tier":"T2"}' % n for n in range(40)]
    payload = valid + "\n" + "\n".join(torn_lines) + "\n"
    (tmp_path / "activation_events.jsonl").write_text(
        payload, encoding="utf-8", newline="")
    scan = pla.run_redaction_scan(tmp_path)
    report = scan["malformed_jsonl_lines"]["activation_events.jsonl"]
    assert report["total"] == 40
    assert report["listed"] == pla._MALFORMED_REPORT_MAX_LINES_PER_FILE
    assert len(report["lines"]) == pla._MALFORMED_REPORT_MAX_LINES_PER_FILE
    assert scan["redaction_status"] == "REDACTED"
