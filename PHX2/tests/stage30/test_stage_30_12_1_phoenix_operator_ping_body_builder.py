"""Stage 30.12.1 PHOENIX operator ping body-builder factory tests.

Proves the committed Stage 30.12.1 factory lets a ceremony feed the committed
Stage 30.12 renderer through the EXISTING Stage 30.11.5 ``compact_body_builder``
seam WITHOUT monkey-patching and WITHOUT editing the Stage 30.11 runner / sink /
gate:

  * the factory returns a callable that yields the rich Stage 30.12 PHOENIX body;
  * it renders ONCE, at construction -- every Stage 30.12 fail-closed (WSOL / bad
    CA / secret-bearing field / over-cap) surfaces BEFORE the runner, never inside
    the no-try/except Stage 30.11.3 sink call;
  * a token-mint mismatch fails closed (no body emitted), never silently;
  * missing optional fields render the literal ``Unknown``, never a fabrication;
  * the pretty body reaches the fake transport through the COMMITTED Stage 30.11.5
    bounded runner -> committed dip gate -> committed Stage 30.11.3 sink, with the
    dip gate still controlling whether the transport is reached -- and with ZERO
    Discord / webhook / network / env / real send;
  * the factory is a clean LEAF (imports only the two Stage 30.12 siblings).

Fake / offline only. No live call, no provider, no Discord, no env read, no real
transport.
"""

from __future__ import annotations

import ast
from decimal import Decimal
from pathlib import Path

import pytest

import PHX2.stage30.stage30_12_1_phoenix_operator_ping_body_builder as BB
from PHX2.stage30.stage30_12_1_phoenix_operator_ping_body_builder import (
    PhoenixOperatorPingContext,
    STAGE30_12_1_CONTEXT_INVALID_TYPE_REASON,
    STAGE30_12_1_TOKEN_MINT_MISMATCH_REASON,
    context_to_input,
    make_phoenix_operator_ping_body_builder,
)
from PHX2.stage30.stage30_12_phoenix_operator_ping_models import (
    PhoenixOperatorPingInput,
    Stage30_12PhoenixOperatorPingError,
    WSOL_QUOTE_MINT,
    is_forbidden_record_field_name,
)
from PHX2.stage30.stage30_11_2_fake_runtime_gate_proof import (
    make_constant_clock,
)
from PHX2.stage30.stage30_11_5_bounded_live_runner import (
    default_bounded_run_config,
    run_stage30_11_5_bounded_live_runner,
)
from PHX2.stage30.stage30_11_5_live_wiring_models import (
    STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
    Stage30_11_5TransportClientResult,
)


PHX2_ROOT: Path = Path(__file__).resolve().parent.parent.parent
STAGE30_ROOT: Path = PHX2_ROOT / "stage30"
FACTORY_BASENAME: str = "stage30_12_1_phoenix_operator_ping_body_builder.py"

_CREATED_AT = "2026-01-01T00:00:00Z"

# Two distinct safe-shape Solana base58 mints (real Pump.fun migrated mints).
VALID_MINT = "Et9km9VRfjeeowsMR1YmjR1GhxXHBatAEVhggxYVfaNe"
OTHER_MINT = "k85BpCNVEcLGCzwgKTi3ho3fRjg5Do8Xpo9VrcMpump"


def _full_context(*, mint: str = VALID_MINT, tier: str = "Tier 1"):
    """A fully-populated context (every optional present, honest synthetic values)."""
    return PhoenixOperatorPingContext(
        token_mint=mint,
        tier_token=tier,
        symbol_or_name=None,
        migration_confirmed=True,
        migration_time_utc="2026-06-06T06:14:10Z",
        market_cap_display="$12.3k",
        liquidity_display="$8.2k",
        current_price="0.0000055",
        ath_price="0.0000110",
        absolute_drawdown="0.0000055",
        fractional_drop_pct="-55.00%",
        tier_band_display=None,
        basis_display="Post-migration ATH",
        source_ref="helius:sig:5hMAYVvmcYNxV29b5TAboHuKEXKjURwU484fjHr:slot:424620715",
        age_display="12.0h",
        ath_market_cap_display="$24.6k",
    )


class _FakeGateInput:
    """A minimal duck-typed Stage 30.9.3-style gate input (only ``token_mint``)."""

    def __init__(self, token_mint) -> None:
        self.token_mint = token_mint


class _RecordingNoSendTransportClient:
    """In-memory Stage 30.11.5 transport client that records the body and ACCEPTS.

    Opens no socket; performs no Discord / webhook send. ``discord_sends`` /
    ``webhook_calls`` are pinned at 0 by construction. Conforms to the committed
    Stage 30.11.5 transport-client protocol (payload -> client result).
    """

    def __init__(self, *, created_at_utc: str) -> None:
        self._created = created_at_utc
        self.attempted = 0
        self.accepted = 0
        self.bodies = []
        self.discord_sends = 0
        self.webhook_calls = 0

    def __call__(self, payload):
        self.attempted += 1
        self.bodies.append(getattr(payload, "body", None))
        self.accepted += 1
        return Stage30_11_5TransportClientResult(
            accepted=True,
            transport_status=STAGE30_11_5_TRANSPORT_ACCEPT_STATUS,
            candidate_id=getattr(payload, "candidate_id", ""),
            token_mint=getattr(payload, "token_mint", ""),
            created_at_utc=self._created,
        )


def _candidate(*, candidate_id: str, mint: str, tier_hint: str) -> dict:
    """Build a flat candidate in the fully-present dip-ready shape the committed
    Stage 30.11.5 assembler accepts (mirrors the committed fake-proof
    ``_projection``: ``post_migration_ath_verified=True`` + ``source_ref`` are
    REQUIRED for the committed dip gate to PASS). Only ``tier_hint`` / ids vary.
    """
    return {
        "candidate_id": candidate_id,
        "token_mint": mint,
        "pair_type": "SOL",
        "tier_hint": tier_hint,
        "drawdown_from_ath": "0.55",
        "migration_status": "PRESENT",
        "ath_status": "PRESENT",
        "market_context_status": "PRESENT",
        "post_migration_ath_verified": True,
        "source_ref": "ref-" + candidate_id,
        "current_market_cap_usd": "12345.67",
        "created_at_utc": _CREATED_AT,
    }


def _eligible_candidate(*, mint: str = VALID_MINT) -> dict:
    """Tier 1, drawdown 0.55 in the 0.50-0.60 band -> assembled -> bridged -> gate
    PASS -> reaches the transport.
    """
    return _candidate(candidate_id="cand-phoenix", mint=mint, tier_hint="Tier 1")


def _ineligible_candidate() -> dict:
    """Tier Unknown non-dip -> assembled -> bridged -> gate SKIP (suppressed BEFORE
    dispatch; the transport is never reached).
    """
    return _candidate(
        candidate_id="cand-unknown", mint="mint-unknown", tier_hint="Tier Unknown"
    )


# ---------------------------------------------------------------------------
# 1-2. Factory returns a callable; the rendered body carries every section
# ---------------------------------------------------------------------------


def test_factory_returns_callable_that_renders_body() -> None:
    builder = make_phoenix_operator_ping_body_builder(_full_context())
    assert callable(builder)
    body = builder(_FakeGateInput(VALID_MINT))
    assert isinstance(body, str) and body != ""


def test_body_contains_expected_sections() -> None:
    builder = make_phoenix_operator_ping_body_builder(_full_context())
    body = builder(_FakeGateInput(VALID_MINT))
    for needle in (
        "\U0001f525 PHOENIX",          # fire + PHOENIX header
        f"CA: {VALID_MINT}",           # full CA line
        "\U0001f9e0 State",            # State section
        "\U0001f4b0 Price",            # Price section
        "\U0001f3af Dip Gate",         # Dip Gate section
        "\U0001f9fe Provenance",       # Provenance section
        "PRIVATE OPERATOR ONLY",       # operator-only footer
    ):
        assert needle in body, f"body missing {needle!r}"


def test_factory_body_contains_ath_market_cap_display() -> None:
    # Stage 30.12.2: the context's ATH market-cap display reaches the State line.
    builder = make_phoenix_operator_ping_body_builder(
        _full_context(mint=VALID_MINT, tier="Tier 1")
    )
    body = builder(_FakeGateInput(VALID_MINT))
    assert "ATH MC: $24.6k" in body


# ---------------------------------------------------------------------------
# 3 + 8. Render-at-construction (not per call)
# ---------------------------------------------------------------------------


def test_render_happens_at_construction_not_per_call(monkeypatch) -> None:
    def _boom(_input):
        raise Stage30_12PhoenixOperatorPingError("FORCED_AT_CONSTRUCTION")

    monkeypatch.setattr(BB, "render_phoenix_operator_ping", _boom)
    # The renderer error surfaces at construction -- make_...() raises and no
    # per-candidate callable is ever returned (the per-call path is unreachable).
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        make_phoenix_operator_ping_body_builder(_full_context())
    assert exc.value.reason == "FORCED_AT_CONSTRUCTION"


def test_renderer_called_once_at_construction_only(monkeypatch) -> None:
    calls = {"n": 0}
    real = BB.render_phoenix_operator_ping

    def _counting(input_record):
        calls["n"] += 1
        return real(input_record)

    monkeypatch.setattr(BB, "render_phoenix_operator_ping", _counting)
    builder = make_phoenix_operator_ping_body_builder(_full_context())
    assert calls["n"] == 1, "construction must render exactly once"
    gi = _FakeGateInput(VALID_MINT)
    builder(gi)
    builder(gi)
    builder(gi)
    assert calls["n"] == 1, "the per-call path must NOT render again"


# ---------------------------------------------------------------------------
# 4. Secret-bearing context fails closed at construction
# ---------------------------------------------------------------------------


def test_secret_bearing_source_ref_fails_closed_at_construction() -> None:
    # An API-credential-bearing provenance ref: the committed renderer's
    # forbidden-substring scan rejects it (the hyphen variant normalizes to the
    # forbidden keyword), so the factory fails closed BEFORE returning a callable.
    secret_src = "helius:sig:" + "api-" + "key=abc123" + ":slot:1"
    ctx = _full_context()._replace(source_ref=secret_src)
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        make_phoenix_operator_ping_body_builder(ctx)
    assert exc.value.reason == "DISPLAY_TEXT_FORBIDDEN_SUBSTRING"


def test_wsol_or_bad_mint_context_fails_closed_at_construction() -> None:
    wsol_ctx = _full_context()._replace(token_mint=WSOL_QUOTE_MINT)
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as e_wsol:
        make_phoenix_operator_ping_body_builder(wsol_ctx)
    assert e_wsol.value.reason == "TOKEN_MINT_IS_WSOL_QUOTE"

    bad_ctx = _full_context()._replace(token_mint="not-base58!")
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as e_bad:
        make_phoenix_operator_ping_body_builder(bad_ctx)
    assert e_bad.value.reason == "TOKEN_MINT_NOT_BASE58"


def test_non_context_fails_closed() -> None:
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        make_phoenix_operator_ping_body_builder({"token_mint": VALID_MINT})
    assert exc.value.reason == STAGE30_12_1_CONTEXT_INVALID_TYPE_REASON
    with pytest.raises(Stage30_12PhoenixOperatorPingError):
        context_to_input(object())


# ---------------------------------------------------------------------------
# 5. Token-mint mismatch guard fails closed (no body emitted)
# ---------------------------------------------------------------------------


def test_token_mint_mismatch_fails_closed_no_body() -> None:
    builder = make_phoenix_operator_ping_body_builder(
        _full_context(mint=VALID_MINT)
    )
    with pytest.raises(Stage30_12PhoenixOperatorPingError) as exc:
        builder(_FakeGateInput(OTHER_MINT))
    assert exc.value.reason == STAGE30_12_1_TOKEN_MINT_MISMATCH_REASON
    # A payload with no token_mint attribute -> None -> mismatch -> fail closed.
    with pytest.raises(Stage30_12PhoenixOperatorPingError):
        builder(object())


# ---------------------------------------------------------------------------
# 6. Missing optional fields render the literal ``Unknown`` (never fabricated)
# ---------------------------------------------------------------------------


def test_missing_optional_fields_render_unknown() -> None:
    ctx = PhoenixOperatorPingContext(token_mint=VALID_MINT, tier_token="Tier 2")
    builder = make_phoenix_operator_ping_body_builder(ctx)
    body = builder(_FakeGateInput(VALID_MINT))
    assert f"CA: {VALID_MINT}" in body
    assert "MC: Unknown" in body          # market_cap_display None
    assert "ATH MC: Unknown" in body      # ath_market_cap_display None
    assert "Now: Unknown" in body         # current_price None
    assert "Age: Unknown" in body         # age_display None
    assert "Tier: Tier 2" in body         # required field echoed
    assert "0" not in "MC: Unknown"       # never a fabricated 0


# ---------------------------------------------------------------------------
# 7. Determinism
# ---------------------------------------------------------------------------


def test_determinism_byte_identical() -> None:
    ctx = _full_context()
    b1 = make_phoenix_operator_ping_body_builder(ctx)
    b2 = make_phoenix_operator_ping_body_builder(ctx)
    gi = _FakeGateInput(VALID_MINT)
    assert b1(gi) == b2(gi)               # same context -> identical body
    assert b1(gi) == b1(gi)               # repeated calls -> identical body


def test_context_to_input_maps_all_fields_one_to_one() -> None:
    ctx = _full_context()
    record = context_to_input(ctx)
    assert isinstance(record, PhoenixOperatorPingInput)
    for field in ctx._fields:
        assert getattr(record, field) == getattr(ctx, field)


# ---------------------------------------------------------------------------
# 9. End-to-end through the COMMITTED Stage 30.11.5 runner -> dip gate -> sink
# ---------------------------------------------------------------------------


def test_end_to_end_through_committed_runner_reaches_fake_transport() -> None:
    context = _full_context(mint=VALID_MINT, tier="Tier 1")
    builder = make_phoenix_operator_ping_body_builder(context)
    expected_body = builder(_FakeGateInput(VALID_MINT))
    client = _RecordingNoSendTransportClient(created_at_utc=_CREATED_AT)

    result = run_stage30_11_5_bounded_live_runner(
        (_eligible_candidate(mint=VALID_MINT),),
        transport_client=client,
        now_seconds=make_constant_clock(Decimal(0)),
        config=default_bounded_run_config(created_at_utc=_CREATED_AT),
        compact_body_builder=builder,
        created_at_utc=_CREATED_AT,
    )
    s = result.summary
    assert s.gate_passed == 1
    assert s.dispatch_attempted == 1
    assert s.dispatch_accepted == 1
    assert s.suppressed_by_gate == 0
    # The committed runner's transport boundary recorded EXACTLY the pretty body.
    assert client.attempted == 1
    assert client.bodies == [expected_body]
    assert "\U0001f525 PHOENIX" in client.bodies[0]
    assert f"CA: {VALID_MINT}" in client.bodies[0]
    # No send of any kind.
    assert client.discord_sends == 0
    assert client.webhook_calls == 0


# ---------------------------------------------------------------------------
# 10. The dip gate still controls whether the transport / builder is reached
# ---------------------------------------------------------------------------


def test_gate_skip_does_not_reach_transport_or_builder() -> None:
    context = _full_context(mint=VALID_MINT, tier="Tier 1")
    inner_builder = make_phoenix_operator_ping_body_builder(context)
    calls = {"n": 0}

    def _counting_builder(gate_input):
        calls["n"] += 1
        return inner_builder(gate_input)

    client = _RecordingNoSendTransportClient(created_at_utc=_CREATED_AT)
    result = run_stage30_11_5_bounded_live_runner(
        (_ineligible_candidate(),),
        transport_client=client,
        now_seconds=make_constant_clock(Decimal(0)),
        config=default_bounded_run_config(created_at_utc=_CREATED_AT),
        compact_body_builder=_counting_builder,
        created_at_utc=_CREATED_AT,
    )
    s = result.summary
    assert s.gate_passed == 0
    assert s.suppressed_by_gate == 1
    assert client.attempted == 0           # transport NOT reached
    assert calls["n"] == 0                  # body builder NOT called on a gate skip
    assert client.discord_sends == 0
    assert client.webhook_calls == 0


# ---------------------------------------------------------------------------
# 11. The factory is a clean LEAF
# ---------------------------------------------------------------------------


def _factory_imports() -> set:
    text = (STAGE30_ROOT / FACTORY_BASENAME).read_text(encoding="utf-8")
    modules = set()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def test_factory_phx2_imports_are_only_the_two_stage30_12_siblings() -> None:
    phx2 = {m for m in _factory_imports() if m.startswith("PHX2.")}
    assert phx2 == {
        "PHX2.stage30.stage30_12_phoenix_operator_ping_models",
        "PHX2.stage30.stage30_12_phoenix_operator_ping_renderer",
    }


def test_factory_non_phx2_imports_are_only_stdlib_typing() -> None:
    non_phx2_roots = {
        m.split(".")[0]
        for m in _factory_imports()
        if not m.startswith("PHX2.")
    }
    assert non_phx2_roots <= {"__future__", "typing"}, (
        f"factory imports non-allowlisted module roots {non_phx2_roots}"
    )


def test_factory_imports_no_runtime_provider_or_io_surface() -> None:
    forbidden = (
        "stage30_9_3",
        "stage30_10",
        "stage30_11",
        "stage27",
        "stage28",
        "stage29",
        "discord",
        "webhook",
        "transport",
        "wallet",
        "signing",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "socket",
        "grpc",
        "sqlite3",
        "pathlib",
    )
    for module in _factory_imports():
        lowered = module.lower()
        for needle in forbidden:
            assert needle not in lowered, (
                f"factory imports a forbidden surface {needle!r} ({module!r})"
            )
    # Exact stdlib modules that must never appear.
    roots = {m.split(".")[0] for m in _factory_imports()}
    for bad in ("os", "json", "time", "datetime", "io"):
        assert bad not in roots, f"factory imports forbidden stdlib {bad!r}"


# ---------------------------------------------------------------------------
# 12. Context field-name hygiene (no secret-class names)
# ---------------------------------------------------------------------------


def test_context_field_names_are_not_secret_class() -> None:
    for name in PhoenixOperatorPingContext._fields:
        assert not is_forbidden_record_field_name(name), (
            f"Stage 30.12.1 context field {name!r} is a forbidden "
            f"secret-class / raw-payload-class name"
        )
    # The two required identity fields are present.
    assert "token_mint" in PhoenixOperatorPingContext._fields
    assert "tier_token" in PhoenixOperatorPingContext._fields
