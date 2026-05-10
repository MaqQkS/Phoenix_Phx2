"""End-to-end engine integration with PreviewPipeline.

Verifies the three hard invariants:

1. Engine return value with ``preview_pipeline=None`` is deep-equal to the
   value produced when a fake pipeline raises immediately.
2. A pipeline that raises does not affect the AlertDecision row in the DB.
3. A slow pipeline does not affect engine return value or correctness.
"""

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Tuple

import pytest

from PHX2.config.settings import PHX2DryRunDbSettings
from PHX2.db.connection import PHX2Connection, get_phx2_connection
from PHX2.db.migrations import apply_stage5c1_schema
from PHX2.db.repositories import (
    ATHRepository,
    DispatchEventRepository,
    PriceObservationRepository,
    TokenSequenceRepository,
    repository_registry,
)
from PHX2.dispatch.dispatcher import Dispatcher
from PHX2.dispatch.preview_pipeline import PreviewPipeline
from PHX2.dispatch.sinks.console import ConsoleSink
from PHX2.dispatch.sinks.discord import DiscordSink
from PHX2.dispatch.sinks.file_preview import FileSink
from PHX2.dispatch.transport.http_client import HttpResponse
from PHX2.models import (
    ATHConfidence,
    ATHEvent,
    ATHEventType,
    ATHState,
    ATHStatus,
    ClockFeatures,
    DataStatus,
    DecisionType,
    FieldFeatures,
    PriceObservation,
    TokenState,
)
from PHX2.renderers.alert_renderer import AlertRenderer
from PHX2.renderers.context import RenderingContextAssembler
from PHX2.services.alert_eligibility_engine import AlertEligibilityEngine


TOKEN = "tokenA"
EVAL_TIME = datetime(2026, 5, 8, 10, 0, 0, tzinfo=timezone.utc)
MIG_TIME = EVAL_TIME - timedelta(hours=1)
ATH_TIME = MIG_TIME + timedelta(minutes=10)


def _temporary_phx2_db_path() -> Path:
    temp_dir = Path("PHX2/.test_tmp")
    temp_dir.mkdir(exist_ok=True)
    return temp_dir / f"engine_int_{uuid.uuid4().hex}.db"


def _cleanup_temporary_phx2_db(path: Path) -> None:
    if path.exists():
        path.unlink()
    try:
        path.parent.rmdir()
    except OSError:
        pass


@contextmanager
def _engine_context(
    *, preview_pipeline=None
) -> Iterator[Tuple[PHX2Connection, AlertEligibilityEngine]]:
    path = _temporary_phx2_db_path()
    connection = get_phx2_connection(PHX2DryRunDbSettings(path=str(path)))
    try:
        apply_stage5c1_schema(connection)
        registry = repository_registry(connection)
        engine = AlertEligibilityEngine(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
            alert_decisions=registry.alert_decisions,
            current_time_provider=lambda: EVAL_TIME,
            preview_pipeline=preview_pipeline,
        )
        yield connection, engine
    finally:
        connection.close()
        _cleanup_temporary_phx2_db(path)


def _insert_eligible_state(connection: PHX2Connection) -> None:
    drawdown = 0.60
    pump = 4.0
    ath_price = 100.0
    ath_mcap = 100000.0
    cur_price = ath_price * (1.0 - drawdown)
    cur_mcap = ath_mcap * (1.0 - drawdown)
    mig_price = cur_price / pump
    mig_mcap = cur_mcap / pump
    obs_time = EVAL_TIME - timedelta(seconds=60)

    TokenSequenceRepository(connection).upsert(
        TokenState(
            token_address=TOKEN,
            symbol="TST",
            pool_address="pool",
            migration_time=MIG_TIME,
            migration_source="test",
            migration_price=mig_price,
            migration_mcap=mig_mcap,
            current_price=cur_price,
            current_mcap=cur_mcap,
            last_price_update=obs_time,
            data_status=DataStatus.OK,
        )
    )
    PriceObservationRepository(connection).insert(
        PriceObservation(
            token_address=TOKEN,
            observed_at=obs_time,
            source="test",
            price=cur_price,
            mcap=cur_mcap,
            data_status=DataStatus.OK,
        )
    )
    ath_repo = ATHRepository(connection)
    ath_event_id = ath_repo.insert_event(
        ATHEvent(
            token_address=TOKEN,
            event_time=ATH_TIME,
            candidate_price=ath_price,
            candidate_mcap=ath_mcap,
            candidate_source="test",
            new_ath_price=ath_price,
            new_ath_mcap=ath_mcap,
            status_before=ATHStatus.UNKNOWN,
            status_after=ATHStatus.CONFIRMED,
            confidence_before=ATHConfidence.UNKNOWN,
            confidence_after=ATHConfidence.HIGH,
            mutation_type=ATHEventType.ATH_RAISED,
            accepted=True,
            data_status=DataStatus.OK,
        )
    )
    ath_repo.upsert_state(
        ATHState(
            token_address=TOKEN,
            ath_price=ath_price,
            ath_mcap=ath_mcap,
            ath_time=ATH_TIME,
            ath_status=ATHStatus.CONFIRMED,
            ath_confidence=ATHConfidence.HIGH,
            ath_source="test",
            last_event_id=ath_event_id,
            data_status=DataStatus.OK,
        )
    )


class _RaisingPipeline:
    def handle(self, alert_decision, as_of_time, alert_decision_id):
        raise RuntimeError("pipeline boom")


class _SleepingPipeline:
    def __init__(self, ms: int) -> None:
        self.ms = ms

    def handle(self, alert_decision, as_of_time, alert_decision_id):
        time.sleep(self.ms / 1000.0)


class _RecordingPipeline:
    def __init__(self) -> None:
        self.calls: list = []

    def handle(self, alert_decision, as_of_time, alert_decision_id):
        self.calls.append((alert_decision, as_of_time, alert_decision_id))


class CommittedRowsRecorder:
    """Wrap a real Dispatcher and record DB state at the moment dispatch fires.

    Used to mechanically verify that the AlertDecision row is already
    queryable when the dispatcher runs — i.e., that the engine commits the
    decision before invoking the preview pipeline.
    """

    def __init__(self, real_dispatcher, connection):
        self._real = real_dispatcher
        self._connection = connection
        self.alert_decisions_count_at_dispatch = None

    def dispatch(self, rendered, alert_decision_id):
        cursor = self._connection.execute(
            "SELECT COUNT(*) FROM alert_decisions WHERE id = ?",
            (alert_decision_id,),
        )
        self.alert_decisions_count_at_dispatch = cursor.fetchone()[0]
        return self._real.dispatch(rendered, alert_decision_id)


def test_engine_with_no_pipeline_produces_baseline_decision():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

    assert decision.decision_type == DecisionType.WOULD_ALERT


def test_engine_decision_is_deep_equal_with_and_without_raising_pipeline():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection)
        baseline = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

    with _engine_context(preview_pipeline=_RaisingPipeline()) as (connection, engine):
        _insert_eligible_state(connection)
        # Should not raise — engine swallows pipeline errors.
        with_pipeline = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

    assert baseline == with_pipeline


def test_raising_pipeline_does_not_affect_alert_decision_row():
    with _engine_context(preview_pipeline=_RaisingPipeline()) as (connection, engine):
        _insert_eligible_state(connection)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        rows = connection.execute(
            "SELECT decision_type, would_alert FROM alert_decisions"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["decision_type"] == "would_alert"
    assert decision.decision_type == DecisionType.WOULD_ALERT


def test_slow_pipeline_does_not_affect_engine_correctness():
    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection)
        baseline = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

    with _engine_context(preview_pipeline=_SleepingPipeline(ms=10)) as (
        connection,
        engine,
    ):
        _insert_eligible_state(connection)
        with_sleep = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

    assert baseline == with_sleep


def test_real_pipeline_writes_jsonl_after_alert_decision_is_committed(
    tmp_path: Path,
):
    routing = {
        "would_alert": {
            "CLEAN": ["file_preview"],
            "PARTIAL": ["file_preview"],
        }
    }
    file_sink = FileSink(root_dir=tmp_path)

    with _engine_context() as (connection, engine):
        # Build the assembler/renderer/dispatcher inside this context so the
        # repositories share the same connection as the engine.
        registry = repository_registry(connection)
        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        renderer = AlertRenderer()
        dispatch_repo = DispatchEventRepository(connection)
        dispatcher = Dispatcher(
            sinks={"file_preview": file_sink},
            repository=dispatch_repo,
            routing_config=routing,
        )
        recorder = CommittedRowsRecorder(dispatcher, connection)
        pipeline = PreviewPipeline(assembler, renderer, recorder)
        engine._preview_pipeline = pipeline

        _insert_eligible_state(connection)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.WOULD_ALERT

        # Ordering: at the moment the dispatcher fired, the AlertDecision row
        # was already queryable — i.e., the engine committed it before the
        # pipeline ran.
        assert recorder.alert_decisions_count_at_dispatch == 1

        # The decision row exists in the DB.
        decision_rows = connection.execute(
            "SELECT id FROM alert_decisions"
        ).fetchall()
        assert len(decision_rows) == 1
        decision_id = decision_rows[0]["id"]

        # The dispatch_events row points at the just-committed decision.
        dispatch_rows = connection.execute(
            "SELECT alert_decision_id, target, status, payload_ref "
            "FROM dispatch_events"
        ).fetchall()
        assert len(dispatch_rows) == 1
        assert dispatch_rows[0]["alert_decision_id"] == decision_id
        assert dispatch_rows[0]["target"] == "file_preview"
        assert dispatch_rows[0]["status"] == "sent"
        assert dispatch_rows[0]["payload_ref"] is not None

        # The JSONL file exists.
        jsonl_path = Path(dispatch_rows[0]["payload_ref"])
        assert jsonl_path.exists()

        # After the View B refactor, the rendered footer surfaces the real
        # decision id (the integer PK), not "unknown" from the dead
        # key_feature_snapshot lookup.
        import json as _json

        with jsonl_path.open("r", encoding="utf-8") as fh:
            payload = _json.loads(fh.readline())
        assert payload["alert_decision_id"] == decision_id
        assert f"Decision:     {decision_id}" in payload["formatted_text"]
        assert "Decision:     unknown" not in payload["formatted_text"]


def test_engine_does_not_directly_invoke_dispatcher_or_assembler():
    """Engine module never imports from PHX2.dispatch except as TYPE_CHECKING."""

    import ast
    from pathlib import Path as _Path

    engine_path = _Path(__file__).resolve().parents[2] / "services" / "alert_eligibility_engine.py"
    source = engine_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    runtime_dispatch_imports = []
    type_checking_dispatch_imports = []

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.in_type_checking = False

        def visit_If(self, node: ast.If) -> None:
            is_tc = (
                isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"
            ) or (
                isinstance(node.test, ast.Attribute)
                and isinstance(node.test.value, ast.Name)
                and node.test.attr == "TYPE_CHECKING"
            )
            if is_tc:
                prior = self.in_type_checking
                self.in_type_checking = True
                self.generic_visit(node)
                self.in_type_checking = prior
            else:
                self.generic_visit(node)

        def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
            module = node.module or ""
            if module.startswith("PHX2.dispatch"):
                if self.in_type_checking:
                    type_checking_dispatch_imports.append(module)
                else:
                    runtime_dispatch_imports.append(module)

    Visitor().visit(tree)

    assert runtime_dispatch_imports == [], (
        f"Engine has runtime imports from PHX2.dispatch: {runtime_dispatch_imports}"
    )


# ----------------------------------------------------------------------------
# Stage 8C: end-to-end through DiscordSink + FakeHttpClient
# ----------------------------------------------------------------------------


class _RecordingHttpClient:
    """In-memory HttpClient: records every POST and returns a 204."""

    def __init__(self) -> None:
        self.post_calls: list = []

    def post(self, url: str, json: dict, timeout: float) -> HttpResponse:
        self.post_calls.append({"url": url, "json": json, "timeout": timeout})
        return HttpResponse(status_code=204, text="", headers={})


def test_real_pipeline_dispatches_to_all_three_sinks_including_discord(
    tmp_path: Path,
):
    """Engine + PreviewPipeline + Dispatcher with file/console/discord sinks.

    Verifies:
    1. Three dispatch_events rows are created (one per sink), all "sent".
    2. DiscordSink invokes its HttpClient exactly once.
    3. The POST payload contains the expected embed shape.
    4. The webhook URL never appears in any dispatch_events row.
    """

    import io

    placeholder_url = "https://example.invalid/webhook"
    fake_client = _RecordingHttpClient()
    file_sink = FileSink(root_dir=tmp_path)
    console_stream = io.StringIO()
    console_sink = ConsoleSink(stream=console_stream)
    discord_sink = DiscordSink(
        webhook_url=placeholder_url, http_client=fake_client
    )

    routing = {
        "would_alert": {
            "CLEAN": ["file_preview", "console", "discord_private_preview"],
            "PARTIAL": ["file_preview", "console", "discord_private_preview"],
        },
        "skip": {"INFO": ["file_preview"]},
        "block": {"INFO": ["file_preview"]},
        "error": {"ERROR": ["file_preview", "console"]},
    }

    with _engine_context() as (connection, engine):
        registry = repository_registry(connection)
        assembler = RenderingContextAssembler(
            token_sequence=registry.token_sequence,
            price_observations=registry.price_observations,
            ath=registry.ath,
            field_features=registry.field_features,
            clock_features=registry.clock_features,
        )
        renderer = AlertRenderer()
        dispatch_repo = DispatchEventRepository(connection)
        dispatcher = Dispatcher(
            sinks={
                "file_preview": file_sink,
                "console": console_sink,
                "discord_private_preview": discord_sink,
            },
            repository=dispatch_repo,
            routing_config=routing,
        )
        pipeline = PreviewPipeline(assembler, renderer, dispatcher)
        engine._preview_pipeline = pipeline

        _insert_eligible_state(connection)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.WOULD_ALERT

        decision_rows = connection.execute(
            "SELECT id FROM alert_decisions"
        ).fetchall()
        decision_id = decision_rows[0]["id"]

        dispatch_rows = connection.execute(
            "SELECT alert_decision_id, target, status, payload_ref, error_message "
            "FROM dispatch_events ORDER BY target"
        ).fetchall()

    assert len(dispatch_rows) == 3
    by_target = {row["target"]: row for row in dispatch_rows}
    assert set(by_target.keys()) == {
        "console",
        "discord_private_preview",
        "file_preview",
    }
    for row in dispatch_rows:
        assert row["status"] == "sent", (
            f"target {row['target']} did not send: {row['error_message']}"
        )
        assert row["alert_decision_id"] == decision_id

    # Discord made exactly one POST.
    assert len(fake_client.post_calls) == 1
    call = fake_client.post_calls[0]
    assert call["url"] == placeholder_url

    # Payload shape: username + embeds[0] with author/title/color.
    payload = call["json"]
    assert "username" in payload
    assert "embeds" in payload
    assert len(payload["embeds"]) == 1
    embed = payload["embeds"][0]
    assert "[PHX2 DRY RUN" in embed["author"]["name"]
    assert embed["title"].startswith("WOULD_ALERT")
    assert isinstance(embed["color"], int)

    # The webhook URL never leaked into dispatch_events.
    for row in dispatch_rows:
        for column in ("error_message", "payload_ref"):
            value = row[column] or ""
            assert placeholder_url not in value, (
                f"webhook URL leaked into dispatch_events.{column} for "
                f"{row['target']}: {value!r}"
            )

    # Sanity check: the webhook URL must not appear in the JSONL artifact either,
    # even though FileSink has no path to receive it.
    file_preview_row = next(r for r in dispatch_rows if r["target"] == "file_preview")
    jsonl_path = Path(file_preview_row["payload_ref"])
    jsonl_text = jsonl_path.read_text(encoding="utf-8")
    assert placeholder_url not in jsonl_text, (
        "Webhook URL must not appear in JSONL output"
    )


# ----------------------------------------------------------------------------
# Stage 8 Patch A: ERROR audit rows flow through PreviewPipeline
# ----------------------------------------------------------------------------


def _install_evaluate_boom(engine, exc: BaseException) -> None:
    """Force engine._evaluate to raise ``exc`` on the next call.

    Mirrors the monkeypatch approach in test_alert_eligibility_engine.py's
    Section 31 test: replace one of the engine's repository methods so the
    exception originates inside _evaluate naturally.
    """

    def _boom(*args, **kwargs):
        raise exc

    engine.field_features.get_latest_at_or_before = _boom  # type: ignore[assignment]


def test_record_error_audit_inserts_error_decision_row():
    """Without a preview_pipeline, an ERROR audit row is still inserted and the
    original engine exception still propagates."""

    with _engine_context() as (connection, engine):
        _insert_eligible_state(connection)
        _install_evaluate_boom(
            engine, ValueError("original engine error")
        )

        with pytest.raises(ValueError, match="original engine error"):
            engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        rows = connection.execute(
            "SELECT decision_type FROM alert_decisions"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["decision_type"] == DecisionType.ERROR.value


def test_record_error_audit_invokes_preview_pipeline_with_decision_id():
    """When _evaluate raises, the ERROR audit row is also routed through the
    PreviewPipeline with the integer id of the just-inserted row."""

    pipeline = _RecordingPipeline()

    with _engine_context(preview_pipeline=pipeline) as (connection, engine):
        _insert_eligible_state(connection)
        _install_evaluate_boom(
            engine, ValueError("original engine error")
        )

        with pytest.raises(ValueError, match="original engine error"):
            engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        rows = connection.execute(
            "SELECT id FROM alert_decisions"
        ).fetchall()
        assert len(rows) == 1
        inserted_decision_id = rows[0]["id"]

    assert len(pipeline.calls) == 1
    decision_arg, as_of_arg, decision_id_arg = pipeline.calls[0]
    assert decision_arg.decision_type == DecisionType.ERROR
    assert decision_id_arg == inserted_decision_id
    assert as_of_arg == EVAL_TIME


def test_pipeline_failure_during_error_audit_does_not_replace_original_exception():
    """If the PreviewPipeline raises while handling the ERROR audit row, the
    pipeline exception is suppressed and the original engine exception is what
    propagates from evaluate_token."""

    with _engine_context(preview_pipeline=_RaisingPipeline()) as (
        connection,
        engine,
    ):
        _insert_eligible_state(connection)
        _install_evaluate_boom(
            engine, ValueError("original engine error")
        )

        with pytest.raises(ValueError) as excinfo:
            engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        assert str(excinfo.value) == "original engine error"
        assert not isinstance(excinfo.value, RuntimeError)

        # The pipeline's RuntimeError("pipeline boom") was caught inside
        # _record_error_audit and must not appear anywhere on the propagated
        # exception's __cause__/__context__ chain.
        chain: list = []
        node = excinfo.value
        while node is not None and node not in chain:
            chain.append(node)
            node = node.__cause__ or node.__context__
        for linked in chain:
            assert not (
                isinstance(linked, RuntimeError)
                and "pipeline boom" in str(linked)
            ), f"pipeline RuntimeError leaked into exception chain: {linked!r}"

        # The audit row was still committed before the pipeline ran.
        rows = connection.execute(
            "SELECT decision_type FROM alert_decisions"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["decision_type"] == DecisionType.ERROR.value


def test_error_dispatch_failure_does_not_corrupt_alert_decisions_row():
    """A pipeline failure during error audit must not leave the audit row in
    a half-written state. The row is committed before the pipeline runs."""

    with _engine_context(preview_pipeline=_RaisingPipeline()) as (
        connection,
        engine,
    ):
        _insert_eligible_state(connection)
        _install_evaluate_boom(
            engine, ValueError("original engine error")
        )

        with pytest.raises(ValueError):
            engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        rows = connection.execute(
            "SELECT token_address, decision_type, evaluated_at, "
            "primary_reason, data_status FROM alert_decisions"
        ).fetchall()

    assert len(rows) == 1
    row = rows[0]
    assert row["token_address"] == TOKEN
    assert row["decision_type"] == DecisionType.ERROR.value
    assert row["primary_reason"] == "error"
    assert row["data_status"] == DataStatus.ERROR.value
    assert row["evaluated_at"] == EVAL_TIME.isoformat()


# ----------------------------------------------------------------------------
# Stage 8 Patch C: end-to-end coverage for non-CLEAN-WOULD_ALERT routes
# ----------------------------------------------------------------------------

# Routing config used by the four sibling tests below. Mirrors the routing in
# test_real_pipeline_dispatches_to_all_three_sinks_including_discord (which
# defines its own local copy and is intentionally not modified here).
_PATCH_C_ROUTING = {
    "would_alert": {
        "CLEAN": ["file_preview", "console", "discord_private_preview"],
        "PARTIAL": ["file_preview", "console", "discord_private_preview"],
    },
    "skip": {"INFO": ["file_preview"]},
    "block": {"INFO": ["file_preview"]},
    "error": {"ERROR": ["file_preview", "console"]},
}


def _make_three_sink_pipeline(connection, tmp_path: Path, placeholder_url: str):
    """Build a PreviewPipeline wired to file/console/discord sinks.

    Returns ``(pipeline, fake_client, console_stream)``. The Discord sink uses
    a FakeHttpClient that records POSTs and returns 204; no real network I/O.
    """
    import io

    fake_client = _RecordingHttpClient()
    file_sink = FileSink(root_dir=tmp_path)
    console_stream = io.StringIO()
    console_sink = ConsoleSink(stream=console_stream)
    discord_sink = DiscordSink(
        webhook_url=placeholder_url, http_client=fake_client
    )

    registry = repository_registry(connection)
    assembler = RenderingContextAssembler(
        token_sequence=registry.token_sequence,
        price_observations=registry.price_observations,
        ath=registry.ath,
        field_features=registry.field_features,
        clock_features=registry.clock_features,
    )
    renderer = AlertRenderer()
    dispatch_repo = DispatchEventRepository(connection)
    dispatcher = Dispatcher(
        sinks={
            "file_preview": file_sink,
            "console": console_sink,
            "discord_private_preview": discord_sink,
        },
        repository=dispatch_repo,
        routing_config=_PATCH_C_ROUTING,
    )
    pipeline = PreviewPipeline(assembler, renderer, dispatcher)
    return pipeline, fake_client, console_stream


def test_real_pipeline_partial_would_alert_dispatches_to_all_three_sinks(
    tmp_path: Path,
):
    """A PARTIAL WOULD_ALERT routes to file/console/discord with PARTIAL marker.

    ``_insert_eligible_state`` inserts token/price/ATH but no field or clock
    features, so the engine flags both as optional_missing and finalizes the
    WOULD_ALERT with ``data_status=PARTIAL``.
    """

    import json as _json
    from PHX2.renderers.adapters.discord import COLOR_PARTIAL

    placeholder_url = "https://example.invalid/webhook"

    with _engine_context() as (connection, engine):
        pipeline, fake_client, _console_stream = _make_three_sink_pipeline(
            connection, tmp_path, placeholder_url
        )
        engine._preview_pipeline = pipeline

        _insert_eligible_state(connection)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.data_status == DataStatus.PARTIAL

        dispatch_rows = connection.execute(
            "SELECT target, status, payload_ref, error_message "
            "FROM dispatch_events ORDER BY target"
        ).fetchall()

    assert len(dispatch_rows) == 3
    by_target = {row["target"]: row for row in dispatch_rows}
    assert set(by_target.keys()) == {
        "console",
        "discord_private_preview",
        "file_preview",
    }
    for row in dispatch_rows:
        assert row["status"] == "sent", (
            f"target {row['target']} did not send: {row['error_message']}"
        )

    # Discord posted exactly once with PARTIAL color and [PARTIAL DATA] marker.
    assert len(fake_client.post_calls) == 1
    embed = fake_client.post_calls[0]["json"]["embeds"][0]
    assert embed["color"] == COLOR_PARTIAL
    assert "[PARTIAL DATA]" in embed["title"]

    # JSONL line carries severity=PARTIAL.
    file_row = by_target["file_preview"]
    jsonl_text = Path(file_row["payload_ref"]).read_text(encoding="utf-8")
    payload = _json.loads(jsonl_text.splitlines()[0])
    assert payload["severity"] == "PARTIAL"

    # Webhook URL never leaks into dispatch_events or JSONL.
    for row in dispatch_rows:
        for column in ("error_message", "payload_ref"):
            value = row[column] or ""
            assert placeholder_url not in value, (
                f"webhook URL leaked into dispatch_events.{column}"
            )
    assert placeholder_url not in jsonl_text


def test_real_pipeline_skip_dispatches_to_file_preview_only(tmp_path: Path):
    """A SKIP decision routes only to file_preview; console/Discord stay quiet.

    With no token state inserted, the engine returns SKIP with primary_reason
    ``token_not_found`` and severity INFO.
    """

    import json as _json

    placeholder_url = "https://example.invalid/webhook"

    with _engine_context() as (connection, engine):
        pipeline, fake_client, _console_stream = _make_three_sink_pipeline(
            connection, tmp_path, placeholder_url
        )
        engine._preview_pipeline = pipeline

        # No state inserted: token_sequence.get returns None → SKIP.
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.SKIP

        dispatch_rows = connection.execute(
            "SELECT target, status, payload_ref, error_message "
            "FROM dispatch_events"
        ).fetchall()

    # Only file_preview was routed.
    assert len(dispatch_rows) == 1
    row = dispatch_rows[0]
    assert row["target"] == "file_preview"
    assert row["status"] == "sent"

    # Discord made zero POSTs.
    assert len(fake_client.post_calls) == 0

    # JSONL line carries decision_type=skip and severity=INFO.
    jsonl_text = Path(row["payload_ref"]).read_text(encoding="utf-8")
    payload = _json.loads(jsonl_text.splitlines()[0])
    assert payload["decision_type"] == "skip"
    assert payload["severity"] == "INFO"

    # Webhook URL absent from every artifact.
    for column in ("error_message", "payload_ref"):
        value = row[column] or ""
        assert placeholder_url not in value
    assert placeholder_url not in jsonl_text


def test_real_pipeline_block_dispatches_to_file_preview_only(tmp_path: Path):
    """A BLOCK decision (policy disabled) routes only to file_preview.

    BLOCK is constructible by overriding ``engine.policy`` with a frozen
    ``AlertPolicy(enabled=False)`` instance — the first guard in ``_evaluate``
    short-circuits to BLOCK with ``primary_reason=policy_disabled``.
    """

    import json as _json
    from PHX2.services.alert_eligibility_engine import AlertPolicy

    placeholder_url = "https://example.invalid/webhook"

    with _engine_context() as (connection, engine):
        pipeline, fake_client, _console_stream = _make_three_sink_pipeline(
            connection, tmp_path, placeholder_url
        )
        engine._preview_pipeline = pipeline
        engine.policy = AlertPolicy(enabled=False)

        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.BLOCK

        dispatch_rows = connection.execute(
            "SELECT target, status, payload_ref, error_message "
            "FROM dispatch_events"
        ).fetchall()

    # Only file_preview was routed.
    assert len(dispatch_rows) == 1
    row = dispatch_rows[0]
    assert row["target"] == "file_preview"
    assert row["status"] == "sent"

    # Discord made zero POSTs.
    assert len(fake_client.post_calls) == 0

    # JSONL line carries decision_type=block and severity=INFO.
    jsonl_text = Path(row["payload_ref"]).read_text(encoding="utf-8")
    payload = _json.loads(jsonl_text.splitlines()[0])
    assert payload["decision_type"] == "block"
    assert payload["severity"] == "INFO"

    # Webhook URL absent from every artifact.
    for column in ("error_message", "payload_ref"):
        value = row[column] or ""
        assert placeholder_url not in value
    assert placeholder_url not in jsonl_text


def test_real_pipeline_error_dispatches_to_file_and_console_only(tmp_path: Path):
    """An engine exception emits an ERROR audit row that flows to file and console.

    ERROR audit rows are deliberately NOT routed to Discord because every
    evaluation produces a new alert_decision_id, so idempotency cannot
    deduplicate repeated errors. Routing recurring engine errors to Discord
    would risk flooding the channel during persistent failures. file_preview
    and console preserve forensic visibility for engine errors.

    The original exception still propagates to the caller (Patch A's contract).
    """

    import json as _json

    placeholder_url = "https://example.invalid/webhook"

    with _engine_context() as (connection, engine):
        pipeline, fake_client, _console_stream = _make_three_sink_pipeline(
            connection, tmp_path, placeholder_url
        )
        engine._preview_pipeline = pipeline

        _insert_eligible_state(connection)
        _install_evaluate_boom(engine, ValueError("kaboom"))

        with pytest.raises(ValueError, match="kaboom"):
            engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)

        decision_rows = connection.execute(
            "SELECT decision_type FROM alert_decisions"
        ).fetchall()
        assert len(decision_rows) == 1
        assert decision_rows[0]["decision_type"] == DecisionType.ERROR.value

        dispatch_rows = connection.execute(
            "SELECT target, status, payload_ref, error_message "
            "FROM dispatch_events ORDER BY target"
        ).fetchall()

    assert len(dispatch_rows) == 2
    by_target = {row["target"]: row for row in dispatch_rows}
    assert set(by_target.keys()) == {"console", "file_preview"}
    for row in dispatch_rows:
        assert row["status"] == "sent", (
            f"target {row['target']} did not send: {row['error_message']}"
        )

    # Discord made zero POSTs — ERROR is not routed to Discord.
    assert len(fake_client.post_calls) == 0

    # JSONL line carries decision_type=error and severity=ERROR.
    file_row = by_target["file_preview"]
    jsonl_text = Path(file_row["payload_ref"]).read_text(encoding="utf-8")
    payload = _json.loads(jsonl_text.splitlines()[0])
    assert payload["decision_type"] == "error"
    assert payload["severity"] == "ERROR"

    # Webhook URL never leaks into dispatch_events or JSONL.
    for row in dispatch_rows:
        for column in ("error_message", "payload_ref"):
            value = row[column] or ""
            assert placeholder_url not in value, (
                f"webhook URL leaked into dispatch_events.{column}"
            )
    assert placeholder_url not in jsonl_text


# ----------------------------------------------------------------------------
# Stage 8 Patch C+: end-to-end coverage for CLEAN WOULD_ALERT
# ----------------------------------------------------------------------------


def _insert_complete_eligible_state(connection: PHX2Connection) -> None:
    """Insert the same state as ``_insert_eligible_state`` plus field/clock
    features so the engine's ``optional_missing`` stays empty and the resulting
    WOULD_ALERT decision finalizes with ``data_status=OK`` (severity CLEAN).
    """

    _insert_eligible_state(connection)
    registry = repository_registry(connection)
    registry.field_features.upsert(
        FieldFeatures(
            token_address=TOKEN,
            as_of_time=EVAL_TIME,
            feature_version="field_v0_test",
            data_status=DataStatus.OK,
        )
    )
    registry.clock_features.upsert(
        ClockFeatures(
            token_address=TOKEN,
            as_of_time=EVAL_TIME,
            feature_version="clock_v0_test",
            data_status=DataStatus.OK,
        )
    )


def test_real_pipeline_clean_would_alert_dispatches_to_all_three_sinks(
    tmp_path: Path,
):
    """A CLEAN WOULD_ALERT routes to file/console/discord without PARTIAL marker.

    Inserts the full set of inputs the engine considers (token/price/ATH plus
    field and clock features) so ``optional_missing`` stays empty. The decision
    finalizes with ``data_status=OK`` and the renderer derives severity CLEAN,
    which propagates through dispatch_events, the JSONL artifact, and the
    Discord embed color/title.
    """

    import json as _json
    from PHX2.renderers.adapters.discord import COLOR_CLEAN

    placeholder_url = "https://example.invalid/webhook"

    with _engine_context() as (connection, engine):
        pipeline, fake_client, _console_stream = _make_three_sink_pipeline(
            connection, tmp_path, placeholder_url
        )
        engine._preview_pipeline = pipeline

        _insert_complete_eligible_state(connection)
        decision = engine.evaluate_token(TOKEN, as_of_time=EVAL_TIME)
        assert decision.decision_type == DecisionType.WOULD_ALERT
        assert decision.data_status == DataStatus.OK
        assert decision.missing_reasons == []

        dispatch_rows = connection.execute(
            "SELECT target, status, payload_ref, error_message "
            "FROM dispatch_events ORDER BY target"
        ).fetchall()

    assert len(dispatch_rows) == 3
    by_target = {row["target"]: row for row in dispatch_rows}
    assert set(by_target.keys()) == {
        "console",
        "discord_private_preview",
        "file_preview",
    }
    for row in dispatch_rows:
        assert row["status"] == "sent", (
            f"target {row['target']} did not send: {row['error_message']}"
        )

    # Discord posted exactly once with CLEAN color and no [PARTIAL DATA] marker.
    assert len(fake_client.post_calls) == 1
    embed = fake_client.post_calls[0]["json"]["embeds"][0]
    assert embed["color"] == COLOR_CLEAN
    assert "[PARTIAL DATA]" not in embed["title"]

    # JSONL line carries severity=CLEAN.
    file_row = by_target["file_preview"]
    jsonl_text = Path(file_row["payload_ref"]).read_text(encoding="utf-8")
    payload = _json.loads(jsonl_text.splitlines()[0])
    assert payload["severity"] == "CLEAN"

    # Webhook URL never leaks into dispatch_events or JSONL.
    for row in dispatch_rows:
        for column in ("error_message", "payload_ref"):
            value = row[column] or ""
            assert placeholder_url not in value, (
                f"webhook URL leaked into dispatch_events.{column}"
            )
    assert placeholder_url not in jsonl_text
