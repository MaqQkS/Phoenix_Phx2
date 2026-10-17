from __future__ import annotations

import json
import re

import pytest

from PHX2.free_tier_producer.ath_state import CentralAthStateStore
from PHX2.free_tier_producer.compat.build26_capture_artifacts import scan_text
from PHX2.free_tier_producer.compat.production_live_artifacts import (
    run_redaction_scan,
)
from PHX2.free_tier_producer.pumpswap_reserves import (
    BUY_LAYOUT_VIRTUAL,
    PumpSwapReserveArtifact,
    RESERVE_SOURCE_BUY_EVENT,
)


MINT = "EkNbQMQYpd4JET5FpZrqbdkYdHXeqocZcBByJpFWpump"
POOL = "ExVW9Wxpr4TnMchukxGwMYM4XYTr3yTKwpqDE35E9seW"
QUOTE = "So11111111111111111111111111111111111111112"

# Synthetic 88-character public Base58 transaction-signature shapes.  These
# reproduce the failed production boundary without copying production values.
SIGNATURE_WSS_0 = "5" + ("K" * 84) + "wss"
SIGNATURE_WSS_147 = "7" + ("p" * 84) + "wss"
SIGNATURE_WS_3 = "9" + ("q" * 85) + "ws"
# Every character of ws/wss/http/https is a valid Base58 character, so the HTTP
# scheme needles were the same latent false positive as the WebSocket one.
SIGNATURE_HTTP_0 = "3" + ("m" * 83) + "http"
SIGNATURE_HTTPS_12 = "4" + ("n" * 82) + "https"


@pytest.mark.parametrize(
    ("signature", "event_index"),
    (
        (SIGNATURE_WSS_0, 0),
        (SIGNATURE_WSS_147, 147),
        (SIGNATURE_WS_3, 3),
        (SIGNATURE_HTTP_0, 0),
        (SIGNATURE_HTTPS_12, 12),
    ),
)
def test_public_base58_event_key_suffix_is_safe(signature: str, event_index: int) -> None:
    assert len(signature) == 88
    assert re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]+", signature)
    assert scan_text(f"{signature}:{event_index}") == []


@pytest.mark.parametrize(
    "text",
    (
        "transaction_signature:event_index",
        "reason_wss:value",
        "status=wss:label",
        "reason_ws:value",
        "reason_http:value",
        "status=https:label",
    ),
)
def test_harmless_structural_colon_text_is_safe(text: str) -> None:
    assert scan_text(text) == []


def test_json_keys_and_values_with_structural_wss_text_are_safe() -> None:
    payload = {
        "reason_wss:value": "status=wss:label",
        "event_key": f"{SIGNATURE_WSS_0}:0",
        "reason_http:value": "status=https:label",
        "http_event_key": f"{SIGNATURE_HTTP_0}:0",
    }
    assert scan_text(json.dumps(payload, sort_keys=True)) == []


def test_runtime_scanner_preserves_every_base58_scheme_suffix_event_key(
    tmp_path,
) -> None:
    """The production scanner itself must pass an artifact holding an event key
    for every scheme spelled in valid Base58, byte-for-byte unchanged."""
    event_keys = {
        "wss_0": f"{SIGNATURE_WSS_0}:0",
        "wss_147": f"{SIGNATURE_WSS_147}:147",
        "ws_3": f"{SIGNATURE_WS_3}:3",
        "http_0": f"{SIGNATURE_HTTP_0}:0",
        "https_12": f"{SIGNATURE_HTTPS_12}:12",
    }
    artifact = tmp_path / "seen_event_keys.json"
    artifact.write_text(json.dumps(event_keys, sort_keys=True), encoding="utf-8")

    result = run_redaction_scan(tmp_path)
    assert result["redaction_status"] == "REDACTED"
    assert result["total_unsafe_hits"] == 0
    assert result["positive_control_ok"] is True
    assert json.loads(artifact.read_text(encoding="utf-8")) == event_keys


def test_neutral_parity_operational_fields_need_no_scanner_exception(
    tmp_path,
) -> None:
    artifact = tmp_path / "parity.jsonl"
    artifact.write_text(
        json.dumps(
            {
                "provider_label": "CONTROL_SOURCE|SHADOW_STREAM",
                "match_status": "CONTROL_ONLY",
                "control_slot": 123,
                "shadow_slot": 123,
                "CONTROL_SOURCE_CONFIGURED": True,
                "SHADOW_AUTH_PRESENT": True,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = run_redaction_scan(tmp_path)
    assert result["redaction_status"] == "REDACTED"
    assert result["total_unsafe_hits"] == 0
    assert result["positive_control_ok"] is True


def test_exact_cutover_shadow_schema_tokens_are_safe(
    tmp_path,
) -> None:
    artifact = tmp_path / "producer_heartbeat.json"
    artifact.write_text(
        json.dumps(
            {
                "provider_telemetry": {
                    "migration_source_mode": (
                        "HELIUS_PRIMARY_CHAINSTACK_SHADOW"
                    ),
                    "primary_migration_source": "HELIUS",
                    "shadow_source": "CHAINSTACK",
                    "parity": {"chainstack_only": 0},
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    result = run_redaction_scan(tmp_path)
    assert result["redaction_status"] == "REDACTED"
    assert result["total_unsafe_hits"] == 0
    assert result["positive_control_ok"] is True


def test_provider_credential_needles_remain_unsafe_without_exceptions(
    tmp_path,
) -> None:
    artifact = tmp_path / "runtime.log"
    artifact.write_text(
        "CHAIN" + "STACK_ENDPOINT=PRESENT\n"
        + "HELIUS_API" + "_KEY=PRESENT\n",
        encoding="utf-8",
    )
    result = run_redaction_scan(tmp_path)
    assert result["redaction_status"] == "REDACTION_VIOLATION"
    assert result["total_unsafe_hits"] > 0


@pytest.mark.parametrize(
    "endpoint",
    (
        "wss" + "://node.example.invalid",
        "ws" + "://node.example.invalid",
        "WSS" + "://node.example.invalid",
        "WS" + "://node.example.invalid",
        "wss" + "://synthetic-user:synthetic-pass@node.example.invalid/stream?api-" + "key=fake",
    ),
)
def test_actual_websocket_uri_scheme_is_unsafe(endpoint: str) -> None:
    hits = scan_text(endpoint)
    assert "WEBSOCKET_URL" in hits
    assert all(endpoint not in hit for hit in hits)


@pytest.mark.parametrize(
    "endpoint",
    (
        "http" + "://node.example.invalid",
        "https" + "://node.example.invalid",
        "HTTP" + "://node.example.invalid",
        "HTTPS" + "://node.example.invalid",
        "https" + "://synthetic-user:synthetic-pass@node.example.invalid/rpc?api-"
        + "key=fake",
    ),
)
def test_actual_http_uri_scheme_is_unsafe(endpoint: str) -> None:
    hits = scan_text(endpoint)
    assert "HTTP_URL" in hits
    assert all(endpoint not in hit for hit in hits)


@pytest.mark.parametrize(
    ("filename", "content"),
    (
        ("payload.json", json.dumps({"endpoint": "wss" + "://node.example.invalid"})),
        ("runtime.log", "connected endpoint=ws" + "://node.example.invalid"),
    ),
)
def test_runtime_scanner_blocks_websocket_uri_in_artifact(
    tmp_path, filename: str, content: str
) -> None:
    (tmp_path / filename).write_text(content, encoding="utf-8")
    result = run_redaction_scan(tmp_path)
    assert result["redaction_status"] == "REDACTION_VIOLATION"
    assert result["total_unsafe_hits"] > 0
    assert "WEBSOCKET_URL" in result["per_file_hits"][filename]
    assert all(content not in hit for hit in result["per_file_hits"][filename])


@pytest.mark.parametrize(
    "synthetic_secret_control",
    (
        "https" + "://api.telegram.org/bot123456:synthetic-token/sendMessage",
        "https" + "://discord.com/api/" + "webhooks/123456/synthetic-token",
        "https" + "://synthetic.chain" + "stack.invalid/rpc",
        "https" + "://public-api.bird" + "eye.invalid?api-" + "key=synthetic",
        "api_" + "key=synthetic-generic-control",
        "bear" + "er synthetic-generic-control",
    ),
)
def test_existing_secret_positive_controls_remain_unsafe(
    synthetic_secret_control: str,
) -> None:
    assert scan_text(synthetic_secret_control)


# ---------------------------------------------------------------------------
# Telegram bot-token detector (2026-07-20 residual re-audit, L-4).
# The scanner covered endpoints, auth headers, api-key shapes, webhooks and
# provider names, but a bare Telegram ``bot<digits>:<secret>`` token -- carrying
# no ``://``, no ``discord.com`` and no ``api-key`` -- would not fire, even
# though the supervisor path is the Telegram production pipeline.  Every token
# below is FABRICATED and assembled in pieces so this source carries no real
# credential and no literal ``botNNN:`` needle of its own.
# ---------------------------------------------------------------------------

# A synthetic 35-char Telegram secret body (valid token-body alphabet only).
_TG_BODY = "AA" + "Gk9Zx1QwEr" + "2TyUi3OpAs" + "4DfGh5JkLm" + "-_z"
assert len(_TG_BODY) == 35


@pytest.mark.parametrize(
    "synthetic_bot_token",
    (
        # Bare token: <bot_id>:<35-char secret>, no scheme, no host, no api-key.
        "8123456789" + ":" + _TG_BODY,
        "123456" + ":" + _TG_BODY,
        # The ``bot``-prefixed API form, still with no ``://`` and no host.
        "bot" + "8123456789" + ":" + _TG_BODY,
        # Embedded in an otherwise-innocent runtime log line.
        "send retry token=" + "bot" + "770000001" + ":" + _TG_BODY + " status=429",
        # The api.telegram.org host without a scheme (no ``://`` to catch it).
        "api.tele" + "gram.org/bot" + "8123456789" + ":" + _TG_BODY + "/sendMessage",
    ),
)
def test_bare_telegram_bot_token_is_unsafe(synthetic_bot_token: str) -> None:
    hits = scan_text(synthetic_bot_token)
    assert "TELEGRAM_BOT_TOKEN" in hits
    # The token body itself is never echoed back as a matched value.
    assert all(_TG_BODY not in hit for hit in hits)


@pytest.mark.parametrize(
    "safe_text",
    (
        # The canonical paid-primary ledger baseline token <64hex>:<size>:<lines>.
        "417e18ec17bc1e894ad4b5ef584de5d6486d1f5ff0e67cba06cbd38cacef55fc:2561:7",
        # A frozen-ledger baseline token.
        "fa7eb26080bb45d82ce583341b3eea1eb3c712ec3dc9555f876eb8ce1a8926fd:5849:16",
        # Clock times and simple ratios must never look like a bot token.
        "12:34:56",
        "elapsed 100000:1 ratio",
        # The bare word and a short id:number pair carry no secret body.
        "robot mode enabled",
        "chat_id -1001234567890 count 42",
        "8123456789:short",
    ),
)
def test_telegram_bot_token_detector_does_not_false_positive(safe_text: str) -> None:
    assert "TELEGRAM_BOT_TOKEN" not in scan_text(safe_text)


# ---------------------------------------------------------------------------
# authorization: context-aware header rule (2026-07-18 false-positive fix).
# The bare "authorization" substring needle aborted the first live acceptance
# window from producer_heartbeat.json because the harmless migration-admission
# metric KEY ``baseline_observed_pre_authorization`` contains the word.  The
# rule now requires a standalone header/field NAME plus ":"/"=" syntax plus a
# nonempty value.  Unsafe shapes below are assembled in pieces so this test
# source itself carries no header-shaped needle.
# ---------------------------------------------------------------------------

_AUTHZ = "authoriz" + "ation"


@pytest.mark.parametrize(
    "identifier_text",
    (
        "baseline_observed_pre_" + _AUTHZ,
        "provider_telemetry.migration_admission.baseline_observed_pre_" + _AUTHZ,
        "pre_" + _AUTHZ + "_count",
        _AUTHZ + "_state",
        _AUTHZ + "_required",
        "send_" + _AUTHZ + "_blocked",
        '{"baseline_observed_pre_' + _AUTHZ + '": 0}',
        json.dumps({"nested": {"deep": {"pre_" + _AUTHZ + "_flag": True,
                                        _AUTHZ + "_state": "OBSERVED"}}},
                   sort_keys=True),
        # Name-only mention and an EMPTY value carry no credential.
        "Authoriz" + "ation:",
        '"' + _AUTHZ + '": ""',
    ),
)
def test_harmless_authorization_identifiers_are_safe(identifier_text: str) -> None:
    assert scan_text(identifier_text) == []


def _representative_heartbeat() -> dict:
    admission = {
        "pool_creations_seen": 3,
        "migration_proof_pass": 1,
        "rejected_direct_pool": 1,
        "rejected_dust_deposit": 1,
        "admitted_true_migrations": 1,
        "immutable_migration_proofs": 1,
        "baseline_observed_pre_" + _AUTHZ: 2,
        "lp_removal_block_mints": 0,
    }
    telemetry = {
        "provider_mode": "PAID_PRIMARY",
        "status": "ACTIVE",
        "active_streams": 2,
        "max_active_streams": 2,
        "migration_admission": admission,
        "fee_lifecycle": {
            "lifecycle_version": "PHX2_FEE_GATE_LIFECYCLE_V1",
            "fee_gate_immature": 1,
            "fee_gate_fresh_confirmed": 1,
            "fee_gate_temporarily_stale": 0,
        },
    }
    return {
        "kind": "FREE_TIER_PRODUCER_HEARTBEAT",
        "producer_mode": "PAID_PRIMARY_TELEGRAM",
        "provider_telemetry": telemetry,
        "last_discovery_window": {
            "kind": "PAID_PROVIDER_DISCOVERY_WINDOW",
            "provider_telemetry": telemetry,
        },
    }


@pytest.mark.parametrize(
    "basename",
    ("producer_heartbeat.json", "producer_summary.json", "safety_report.json"),
)
def test_representative_runtime_artifact_with_metric_key_is_safe(basename: str) -> None:
    payload = _representative_heartbeat()
    if basename == "producer_summary.json":
        payload = {"kind": "FREE_TIER_PRODUCER_SUMMARY",
                   "outcome": "ZERO_SEND",
                   "provider_telemetry": payload["provider_telemetry"]}
    elif basename == "safety_report.json":
        payload = {"kind": "PRODUCTION_LIVE_SAFETY_REPORT",
                   "verdict": "PASS",
                   "provider_telemetry": payload["provider_telemetry"]}
    assert scan_text(json.dumps(payload, sort_keys=True)) == []


@pytest.mark.parametrize(
    "unsafe_header",
    (
        "Authoriz" + "ation: Be" + "arer synthetic-secret",
        "authoriz" + "ation=Be" + "arer synthetic-secret",
        '"Authoriz' + 'ation": "Basic synthetic-value"',
        "authoriz" + "ation: to" + "ken synthetic-value",
        "AUTHORIZ" + "ATION: SYNTHETIC-VALUE",
        "2026-07-18T00:00:00Z retry send header Authoriz" + "ation: synthetic-cred",
        json.dumps({"headers": {"Authoriz" + "ation": "synthetic-cred"}}),
        "Proxy-Authoriz" + "ation: synthetic-cred",
    ),
)
def test_credential_bearing_authorization_headers_are_unsafe(unsafe_header: str) -> None:
    hits = scan_text(unsafe_header)
    assert "AUTHORIZATION_HEADER" in hits
    # Categories are stable tokens; the credential text itself never appears.
    assert all("synthetic" not in hit.lower() for hit in hits)


def test_runtime_scanner_passes_metric_artifacts_then_blocks_injected_header(
    tmp_path,
) -> None:
    """The exact production scanner over the exact artifact trio that aborted
    the 2026-07-18 acceptance window: clean with the metric key present, then
    REDACTION_VIOLATION once a synthetic credential header is injected — with
    only the safe category and file path in the report, never the value."""

    heartbeat = _representative_heartbeat()
    summary = {"kind": "FREE_TIER_PRODUCER_SUMMARY",
               "provider_telemetry": heartbeat["provider_telemetry"]}
    safety = {"kind": "PRODUCTION_LIVE_SAFETY_REPORT",
              "provider_telemetry": heartbeat["provider_telemetry"]}
    for name, payload in (("producer_heartbeat.json", heartbeat),
                          ("producer_summary.json", summary),
                          ("safety_report.json", safety)):
        (tmp_path / name).write_text(
            json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")

    clean = run_redaction_scan(tmp_path)
    assert clean["redaction_status"] == "REDACTED"
    assert clean["total_unsafe_hits"] == 0
    assert clean["positive_control_ok"] is True
    assert "AUTHORIZATION_HEADER" in clean["positive_control_flagged"]

    injected = "Authoriz" + "ation: Be" + "arer synthetic-injected-credential"
    (tmp_path / "runtime.log").write_text(
        "send retry with header " + injected, encoding="utf-8")
    unsafe = run_redaction_scan(tmp_path)
    assert unsafe["redaction_status"] == "REDACTION_VIOLATION"
    assert unsafe["total_unsafe_hits"] > 0
    hits = unsafe["per_file_hits"]["runtime.log"]
    assert "AUTHORIZATION_HEADER" in hits
    report_text = json.dumps(unsafe, sort_keys=True)
    assert "synthetic-injected-credential" not in report_text
    # The metric-bearing artifacts stay clean even in the violating scan.
    for name in ("producer_heartbeat.json", "producer_summary.json",
                 "safety_report.json"):
        assert unsafe["per_file_hits"][name] == []


def _event(timestamp: int) -> PumpSwapReserveArtifact:
    return PumpSwapReserveArtifact(
        raw_quote_reserves=90_000_000_000,
        virtual_quote_reserves=5_000_000_000,
        effective_quote_reserves=95_000_000_000,
        base_reserves=1_000_000_000_000,
        reserve_source=RESERVE_SOURCE_BUY_EVENT,
        observation_timestamp=f"1970-01-01T00:16:{timestamp - 960:02d}Z",
        decoder_layout_version=BUY_LAYOUT_VIRTUAL,
        pool_address=POOL,
        base_mint=MINT,
        quote_mint=QUOTE,
        base_decimals=6,
        quote_decimals=9,
        event_side="BUY",
        event_timestamp=timestamp,
        base_supply=1_000_000_000_000_000,
    )


def test_runtime_scanner_preserves_ath_checkpoint_event_keys_and_blocks_real_endpoint(
    tmp_path,
) -> None:
    event_keys = (
        f"{SIGNATURE_WSS_0}:0",
        f"{SIGNATURE_WSS_147}:147",
    )
    store = CentralAthStateStore(tmp_path)
    assert store.register_pool(
        mint=MINT,
        pool_address=POOL,
        quote_mint=QUOTE,
        creation_timestamp="1970-01-01T00:16:40Z",
    )
    assert store.observe_quote_price(QUOTE, "1", observed_at=1000)
    assert store.observe_event(
        mint=MINT,
        artifact=_event(1000),
        transaction_signature=SIGNATURE_WSS_0,
        event_index=0,
    )
    assert store.observe_event(
        mint=MINT,
        artifact=_event(1001),
        transaction_signature=SIGNATURE_WSS_147,
        event_index=147,
    )

    checkpoint_path = tmp_path / "ath_state_checkpoint.json"

    def _checkpoint_event_keys() -> tuple:
        # PHX2-E2E-005: the restart checkpoint is the authenticated envelope;
        # the durable event-dedupe keys live in its digest-bound records.
        document = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        (record,) = [r for r in document["payload"]["records"]
                     if r["token_mint"] == MINT]
        return tuple(record["seen_event_keys"])

    assert _checkpoint_event_keys() == event_keys

    clean = run_redaction_scan(tmp_path)
    assert clean["redaction_status"] == "REDACTED"
    assert clean["total_unsafe_hits"] == 0
    assert _checkpoint_event_keys() == event_keys

    endpoint = "wss" + "://node.example.invalid/stream?api-" + "key=synthetic"
    (tmp_path / "runtime.log").write_text(
        "connection refused endpoint=" + endpoint,
        encoding="utf-8",
    )
    unsafe = run_redaction_scan(tmp_path)
    assert unsafe["redaction_status"] == "REDACTION_VIOLATION"
    assert unsafe["total_unsafe_hits"] > 0
    assert "WEBSOCKET_URL" in unsafe["per_file_hits"]["runtime.log"]
    assert all(endpoint not in hit for hit in unsafe["per_file_hits"]["runtime.log"])
    assert _checkpoint_event_keys() == event_keys
