"""Stage 28.7 longer-session smoke harness.

Stage 28.7 ships a deterministic, offline-only smoke harness that
drives the Stage 28.6 bounded private session runner over a
caller-supplied synthetic Stage 28.6 candidate stream using a
caller-injected Stage 28.6 fake transport. The harness exists so
the operator can prove the Stage 28.1 / 28.2 / 28.3a / 28.3b /
28.4 / 28.5 / 28.6 reliability composition can run a longer
private session in controlled conditions, produce the expected
heartbeat / health-snapshot / final-summary artifacts, protect
dedupe, and emit a redaction-safe smoke summary -- without
opening any network connection, without reading any environment
variable, without contacting any real provider, and without
sending any real Discord message.

Stage 28.7 is the proof stage. Stage 28.7 ships NO live smoke
callable in production code, NO real Discord send, NO real
provider connection, NO uncontrolled session, NO daemon /
service / watchdog / autorestart service, NO public routing, NO
subscriber routing, NO paid tier routing, NO X / social, NO
Telegram, NO Stage 29 enforcement, NO automated trading, NO
wallet / private-key / signer logic, NO position sizing, NO
trade execution, NO dashboard / HTTP control server. Controlled
live smoke is documented in
``STAGE_28_CONTROLLED_LIVE_SMOKE_RUNBOOK.md`` and must be
performed manually by the operator after Stage 28.7 closes -- it
is not implemented in this production module.

Stage 28.7 also ships NO Stage 28 closure / no
``stage-28-closed`` tag / no Stage 28-wide manifest. Closure
audit + Stage 29 handoff are Stage 28.8 scope.

Discipline:

  * No env reads. ``os.environ`` / ``os.getenv`` / ``os.environb``
    are never touched here.
  * No direct network library import. No ``urllib`` / ``socket``
    / ``http.client`` / ``ssl`` / ``requests`` / ``httpx`` /
    ``aiohttp`` / ``websockets`` / ``grpc`` / messaging / RPC /
    DB / scheduler / secrets-management library.
  * No sleep / no scheduling / no backoff execution / no queue /
    no thread / no async / no subprocess.
  * The harness does not install OS signal handlers.
  * Caller-supplied paths are validated by the underlying Stage
    28.5 writers; the harness adds no extra path handling beyond
    refusing a non-Path / missing / non-directory output dir.
  * Every output artifact carries only closed-set tokens + safe
    counters + safe identifiers; webhook URLs, provider
    endpoints, API keys, bearer tokens, auth headers, wallet /
    signer fields, raw response bodies, raw exception messages
    must never reach disk via Stage 28.7.

This module imports only stdlib (``json`` / ``pathlib`` /
``typing``) plus the Stage 28.2 / 28.3a / 28.3b / 28.4 / 28.5 /
28.6 production modules. It does NOT import Stage 21-27
production code, does NOT import Stage 28.1 production code
(provider-neutral readiness is a caller-side concern), does NOT
import any network / RPC / messaging / DB / scheduler /
secrets-management library, does NOT read the process
environment, does NOT define a CLI surface, and contains no
top-level I/O.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import (
    Iterable,
    Mapping,
    NamedTuple,
    Optional,
    Tuple,
)

from PHX2.stage28.audited_http_transport_models import (
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_SENT_OK,
    WEBHOOK_IDENTITY_PRIVATE_OPERATOR,
)
from PHX2.stage28.bounded_private_session_runner import (
    Stage28_6BoundedPrivateSessionRunner,
)
from PHX2.stage28.session_runner_models import (
    CANDIDATE_PAIR_STATUS_DISAGREE,
    CANDIDATE_PAIR_STATUS_OK,
    CANDIDATE_PAIR_STATUS_UNKNOWN,
    CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
    CANDIDATE_PRICE_STATUS_MISSING,
    CANDIDATE_PRICE_STATUS_OK,
    CANDIDATE_PRICE_STATUS_STALE,
    Stage28_6CandidateEvent,
    Stage28_6FakeTransport,
    Stage28_6PrivateTransport,
    Stage28_6RunnerConfig,
    Stage28_6RunSummary,
    build_candidate_event,
    build_runner_config,
)


# ---------------------------------------------------------------------------
# Stage 28.7 version axes
# ---------------------------------------------------------------------------


STAGE28_7_MINOR_VERSION: str = "28.7"
STAGE28_7_SCHEMA_VERSION: str = (
    "stage28_7_longer_session_smoke_harness_v0"
)


# Distinctive Stage 28.7 redaction token. Distinct from the Stage
# 27 / 28.1-6 redaction tokens so a leak-scan test for one cannot
# collide with another.
STAGE28_7_REDACTION_TOKEN: str = "<<STAGE28_7_REDACTED>>"


# ---------------------------------------------------------------------------
# Closed-set smoke status vocabulary
# ---------------------------------------------------------------------------


SMOKE_STATUS_OK: str = "OK"
SMOKE_STATUS_DEGRADED: str = "DEGRADED"
SMOKE_STATUS_REFUSED: str = "REFUSED"


SMOKE_STATUS_VALUES: tuple[str, ...] = (
    SMOKE_STATUS_OK,
    SMOKE_STATUS_DEGRADED,
    SMOKE_STATUS_REFUSED,
)


# ---------------------------------------------------------------------------
# Closed-set redaction-scan status vocabulary
# ---------------------------------------------------------------------------


SMOKE_REDACTION_STATUS_SAFE: str = "SAFE"
SMOKE_REDACTION_STATUS_FAILED: str = "FAILED"
SMOKE_REDACTION_STATUS_NOT_SCANNED: str = "NOT_SCANNED"


SMOKE_REDACTION_STATUS_VALUES: tuple[str, ...] = (
    SMOKE_REDACTION_STATUS_SAFE,
    SMOKE_REDACTION_STATUS_FAILED,
    SMOKE_REDACTION_STATUS_NOT_SCANNED,
)


# ---------------------------------------------------------------------------
# Closed-set smoke safe-reason vocabulary
# ---------------------------------------------------------------------------


SMOKE_SAFE_REASON_CODE_OK: str = "SMOKE_OFFLINE_OK"
SMOKE_SAFE_REASON_CODE_DEGRADED: str = "SMOKE_OFFLINE_DEGRADED"
SMOKE_SAFE_REASON_CODE_REDACTION_FAILED: str = (
    "SMOKE_REDACTION_FAILED"
)
SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_MISSING: str = (
    "SMOKE_OUTPUT_DIR_MISSING"
)
SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_NOT_DIR: str = (
    "SMOKE_OUTPUT_DIR_NOT_DIRECTORY"
)
SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE: str = (
    "SMOKE_OUTPUT_DIR_UNSAFE"
)
SMOKE_SAFE_REASON_CODE_ARTIFACT_WRITE_FAILED: str = (
    "SMOKE_ARTIFACT_WRITE_FAILED"
)


SMOKE_SAFE_REASON_CODE_VALUES: tuple[str, ...] = (
    SMOKE_SAFE_REASON_CODE_OK,
    SMOKE_SAFE_REASON_CODE_DEGRADED,
    SMOKE_SAFE_REASON_CODE_REDACTION_FAILED,
    SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_MISSING,
    SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_NOT_DIR,
    SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE,
    SMOKE_SAFE_REASON_CODE_ARTIFACT_WRITE_FAILED,
)


# ---------------------------------------------------------------------------
# Stage 28.7 artifact basenames
# ---------------------------------------------------------------------------


HEARTBEAT_ARTIFACT_BASENAME: str = "stage28_7_heartbeat.jsonl"
HEALTH_SNAPSHOT_ARTIFACT_BASENAME: str = (
    "stage28_7_health_snapshot.json"
)
FINAL_SUMMARY_ARTIFACT_BASENAME: str = (
    "stage28_7_final_run_summary.json"
)
SMOKE_SUMMARY_ARTIFACT_BASENAME: str = (
    "stage28_7_smoke_summary.json"
)
REDACTION_SCAN_ARTIFACT_BASENAME: str = (
    "stage28_7_redaction_scan.json"
)


STAGE28_7_ARTIFACT_BASENAMES: tuple[str, ...] = (
    HEARTBEAT_ARTIFACT_BASENAME,
    HEALTH_SNAPSHOT_ARTIFACT_BASENAME,
    FINAL_SUMMARY_ARTIFACT_BASENAME,
    SMOKE_SUMMARY_ARTIFACT_BASENAME,
    REDACTION_SCAN_ARTIFACT_BASENAME,
)


# ---------------------------------------------------------------------------
# Redaction-scan forbidden substrings
# ---------------------------------------------------------------------------


# Forbidden artifact substrings the redaction scan looks for in
# every Stage 28.7 output artifact. The substrings are
# concatenated literally so this source file itself does not
# carry the literal prefix a downstream string-leak scan would
# flag.
STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS: tuple[str, ...] = (
    # URL schemes.
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "://",
    # Discord webhook host literals.
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    # Slack webhook host literal (defensive).
    "hooks" + ".slack.com",
    # RPC / provider host fragments.
    "helius" + ".xyz",
    "helius" + ".rpc.com",
    "birdeye" + ".so",
    "chainstack" + ".com",
    # Auth header / bearer / api-key fragments.
    "b" + "earer ",
    "a" + "uthorization:",
    "x-a" + "pi-key",
    "x-A" + "pi-Key",
    "api_" + "key",
    "api-" + "key",
    # API-key prefix conventions.
    "s" + "k-",
    "p" + "k-",
    # Common env-variable leak prefixes.
    "DISCORD_WEBHOOK" + "_URL=",
    "HELIUS_API" + "_KEY=",
    "HELIUS_RPC" + "_URL=",
    "HELIUS_GRPC" + "_ENDPOINT=",
    "PHX2_PROVIDER_GRPC" + "_ENDPOINT=",
    # Wallet / signer / private key fragments.
    "private_" + "key",
    "wallet_" + "seed",
    "wallet_" + "address",
    "signer_" + "address",
    # Raw Discord response body leak fragments.
    "raw_" + "response",
    "response_" + "body",
    "raw_" + "payload",
    "payload_" + "blob",
)


# ---------------------------------------------------------------------------
# Exception hierarchy (module-local)
# ---------------------------------------------------------------------------


class Stage28_7SmokeHarnessError(Exception):
    """Base type for every Stage 28.7 smoke-harness error.

    Module-local; not a subclass of any central PHX2 error
    registry. Raw secret values must never reach the constructor;
    callers redact at the call site.
    """


class Stage28_7OutputDirError(Stage28_7SmokeHarnessError):
    """Raised when the caller-supplied output directory fails
    validation.

    Carries only the closed-set safe-reason token + an optional
    safe basename label; never echoes the raw rejected path or any
    secret-looking substring.
    """

    def __init__(
        self,
        *,
        reason: str,
        safe_basename: Optional[str] = None,
    ) -> None:
        self.reason: str = reason
        self.safe_basename: Optional[str] = safe_basename
        super().__init__(
            f"Stage 28.7 smoke harness output dir refused: "
            f"reason={reason!r} safe_basename={safe_basename!r}"
        )


class Stage28_7ArtifactWriteError(Stage28_7SmokeHarnessError):
    """Raised when a Stage 28.7 artifact (smoke summary /
    redaction scan) write fails.

    Carries only the operation token + optional safe basename
    label; the raw OSError text is intentionally dropped.
    """

    def __init__(
        self,
        *,
        operation: str,
        safe_basename: Optional[str] = None,
    ) -> None:
        self.operation: str = operation
        self.safe_basename: Optional[str] = safe_basename
        super().__init__(
            f"Stage 28.7 artifact write failed: "
            f"operation={operation!r} safe_basename={safe_basename!r}"
        )


# ---------------------------------------------------------------------------
# Stage 28.7 smoke summary record
# ---------------------------------------------------------------------------


STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "smoke_status",
    "run_id",
    "session_id",
    "smoke_id",
    "output_dir_safe_label",
    "heartbeat_artifact_basename",
    "health_snapshot_artifact_basename",
    "final_summary_artifact_basename",
    "smoke_summary_artifact_basename",
    "redaction_scan_artifact_basename",
    "offline_candidate_count",
    "events_seen",
    "candidates_seen",
    "dispatch_attempts",
    "dispatch_success",
    "dispatch_failure",
    "retries_attempted",
    "duplicate_suppressed",
    "ambiguous_suppressed",
    "suppressed_count",
    "heartbeat_count",
    "stop_reason",
    "final_health_status",
    "redaction_status",
    "live_send_attempted",
    "live_send_count",
    "safe_reason_code",
)


class Stage28_7SmokeSummary(NamedTuple):
    """Immutable Stage 28.7 smoke summary.

    All fields are closed-set tokens / safe identifiers / safe
    counters / safe basenames. The record never carries a webhook
    URL, provider endpoint, RPC URL, API key, bearer token, auth
    header, private key, wallet seed, raw response body, raw env
    value, secret-like path, or raw exception string.
    """

    schema_version: str
    smoke_status: str
    run_id: str
    session_id: str
    smoke_id: str
    output_dir_safe_label: str
    heartbeat_artifact_basename: str
    health_snapshot_artifact_basename: str
    final_summary_artifact_basename: str
    smoke_summary_artifact_basename: str
    redaction_scan_artifact_basename: str
    offline_candidate_count: int
    events_seen: int
    candidates_seen: int
    dispatch_attempts: int
    dispatch_success: int
    dispatch_failure: int
    retries_attempted: int
    duplicate_suppressed: int
    ambiguous_suppressed: int
    suppressed_count: int
    heartbeat_count: int
    stop_reason: str
    final_health_status: str
    redaction_status: str
    live_send_attempted: bool
    live_send_count: int
    safe_reason_code: str


def smoke_summary_to_dict(
    summary: Stage28_7SmokeSummary,
) -> dict:
    """Project a smoke summary record into a deterministic-order
    dict suitable for canonical JSON encoding.

    Pure / deterministic.
    """
    if not isinstance(summary, Stage28_7SmokeSummary):
        raise Stage28_7SmokeHarnessError(
            "smoke_summary_to_dict requires a Stage28_7SmokeSummary"
        )
    return {
        name: getattr(summary, name)
        for name in STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES
    }


def canonical_smoke_summary_json(
    summary: Stage28_7SmokeSummary,
) -> str:
    """Return the canonical JSON encoding of a smoke summary.

    Stable across runs: ``sort_keys=True``, ``separators=(",",
    ":")``, ``ensure_ascii=False``. Pure / deterministic.
    """
    return json.dumps(
        smoke_summary_to_dict(summary),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


# ---------------------------------------------------------------------------
# Stage 28.7 redaction-scan result
# ---------------------------------------------------------------------------


STAGE28_7_REDACTION_SCAN_FIELD_NAMES: tuple[str, ...] = (
    "schema_version",
    "redaction_status",
    "files_scanned",
    "offending_basenames",
    "offending_substrings",
)


class Stage28_7RedactionScanResult(NamedTuple):
    """Immutable Stage 28.7 redaction-scan result.

    ``files_scanned`` is a tuple of safe basenames (sorted).
    ``offending_basenames`` / ``offending_substrings`` carry only
    safe basenames / closed-set substring labels; they never
    carry the offending file's body.
    """

    schema_version: str
    redaction_status: str
    files_scanned: tuple[str, ...]
    offending_basenames: tuple[str, ...]
    offending_substrings: tuple[str, ...]


def redaction_scan_to_dict(
    result: Stage28_7RedactionScanResult,
) -> dict:
    if not isinstance(result, Stage28_7RedactionScanResult):
        raise Stage28_7SmokeHarnessError(
            "redaction_scan_to_dict requires a "
            "Stage28_7RedactionScanResult"
        )
    return {
        "schema_version": result.schema_version,
        "redaction_status": result.redaction_status,
        "files_scanned": list(result.files_scanned),
        "offending_basenames": list(result.offending_basenames),
        "offending_substrings": list(result.offending_substrings),
    }


def canonical_redaction_scan_json(
    result: Stage28_7RedactionScanResult,
) -> str:
    return json.dumps(
        redaction_scan_to_dict(result),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


# ---------------------------------------------------------------------------
# Output-directory validation
# ---------------------------------------------------------------------------


_OUTPUT_DIR_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "h" + "ttps://",
    "h" + "ttp://",
    "w" + "ss://",
    "w" + "s://",
    "discord" + ".com",
    "discord" + "app.com",
    "/webhooks/",
    "hooks" + ".slack.com",
    "b" + "earer ",
    "a" + "uthorization:",
    "s" + "k-",
    "p" + "k-",
)


def _safe_basename_for_label(directory: Path) -> str:
    """Return a short safe basename label for an output
    directory.

    The label is the directory's bare name with all non-allowlisted
    characters dropped and any forbidden substring substituted by
    the Stage 28.7 redaction token. The harness never echoes the
    full caller-supplied path.
    """
    candidate = directory.name
    if not isinstance(candidate, str) or candidate == "":
        return STAGE28_7_REDACTION_TOKEN
    allowed: str = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.-"
    )
    filtered = "".join(
        ch for ch in candidate if ch in allowed
    )
    if filtered == "":
        return STAGE28_7_REDACTION_TOKEN
    if filtered[0] in {".", "-"}:
        filtered = "_" + filtered[1:]
    lowered = filtered.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            return STAGE28_7_REDACTION_TOKEN
    if len(filtered) > 64:
        filtered = filtered[:64]
    return filtered


def _validate_output_dir(directory: Path) -> str:
    """Validate the caller-supplied output directory and return a
    safe label for the smoke summary.

    Rules:

      * the caller must supply an explicit ``Path``,
      * the path must exist and be a directory (the harness never
        creates the output directory itself; the caller owns the
        scratch space),
      * the path string must not contain any secret-looking
        substring.
    """
    if not isinstance(directory, Path):
        raise Stage28_7OutputDirError(
            reason=SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE,
        )
    path_str = str(directory)
    lowered = path_str.lower()
    for needle in _OUTPUT_DIR_FORBIDDEN_SUBSTRINGS:
        if needle in lowered:
            raise Stage28_7OutputDirError(
                reason=SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE,
            )
    if not directory.exists():
        raise Stage28_7OutputDirError(
            reason=SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_MISSING,
            safe_basename=_safe_basename_for_label(directory),
        )
    if not directory.is_dir():
        raise Stage28_7OutputDirError(
            reason=SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_NOT_DIR,
            safe_basename=_safe_basename_for_label(directory),
        )
    return _safe_basename_for_label(directory)


# ---------------------------------------------------------------------------
# Synthetic Stage 28.6 candidate builder
# ---------------------------------------------------------------------------


_SYNTHETIC_WEBHOOK_IDENTITY: str = WEBHOOK_IDENTITY_PRIVATE_OPERATOR
_SYNTHETIC_EVENT_KIND: str = "smoke_event"
_SYNTHETIC_PING_TYPE: str = "smoke_ping"


def _synthetic_candidate(
    *,
    index: int,
    token_mint: str,
    pair_quote_asset: str,
    pair_status: str,
    price_status: str,
    malformed: bool = False,
    dispatch_allowed: bool = True,
    duplicate_of_index: Optional[int] = None,
) -> Stage28_6CandidateEvent:
    """Build a deterministic Stage 28.6 candidate for the smoke
    harness.

    The ``duplicate_of_index`` argument lets a later candidate
    share the dedupe key of an earlier one so the runner exercises
    the Stage 28.2 ledger duplicate-suppression path.
    """
    dedupe_index = (
        index if duplicate_of_index is None else duplicate_of_index
    )
    normalized_event_id = f"smoke_event_{dedupe_index:02d}"
    return build_candidate_event(
        event_id=f"smoke_event_{index:02d}",
        token_mint=token_mint,
        pair_quote_asset=pair_quote_asset,
        event_kind=_SYNTHETIC_EVENT_KIND,
        ping_type=_SYNTHETIC_PING_TYPE,
        normalized_event_id=normalized_event_id,
        rendered_payload={
            "content": f"smoke event {index:02d}",
            "embeds": [],
        },
        pre_send_artifact_reference=(
            f"smoke_ping_{index:02d}_payload.json"
        ),
        webhook_identity=_SYNTHETIC_WEBHOOK_IDENTITY,
        dispatch_allowed=dispatch_allowed,
        pair_status=pair_status,
        price_status=price_status,
        malformed=malformed,
    )


def build_stage28_7_synthetic_candidates() -> Tuple[
    Stage28_6CandidateEvent, ...
]:
    """Return a deterministic tuple of Stage 28.6 candidate events
    exercising the Stage 28.6 runner's success / suppression /
    duplicate paths.

    Coverage:

      * candidate 0: dispatchable SOL candidate (success path),
      * candidate 1: dispatchable SOL candidate (different mint),
      * candidate 2: duplicate of candidate 0 (duplicate
        terminal suppression),
      * candidate 3: UNKNOWN pair (suppressed by Stage 27 pair
        rule),
      * candidate 4: DISAGREE pair (suppressed by Stage 27 pair
        rule),
      * candidate 5: USDC observe-only (suppressed by Stage 27
        pair rule),
      * candidate 6: STALE price (suppressed by Stage 25-shape
        price rule),
      * candidate 7: MISSING price (suppressed),
      * candidate 8: malformed flag set (suppressed),
      * candidate 9: dispatch_allowed=False (treated as
        malformed by the runner's defensive branch).

    The tuple is in input order; tests may pin per-index counts
    deterministically.
    """
    return (
        _synthetic_candidate(
            index=0,
            token_mint="SmokeMint00",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_OK,
        ),
        _synthetic_candidate(
            index=1,
            token_mint="SmokeMint01",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_OK,
        ),
        _synthetic_candidate(
            index=2,
            token_mint="SmokeMint00",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_OK,
            duplicate_of_index=0,
        ),
        _synthetic_candidate(
            index=3,
            token_mint="SmokeMintUnk03",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_UNKNOWN,
            price_status=CANDIDATE_PRICE_STATUS_OK,
        ),
        _synthetic_candidate(
            index=4,
            token_mint="SmokeMintDis04",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_DISAGREE,
            price_status=CANDIDATE_PRICE_STATUS_OK,
        ),
        _synthetic_candidate(
            index=5,
            token_mint="SmokeMintUsdc05",
            pair_quote_asset="USDC",
            pair_status=CANDIDATE_PAIR_STATUS_USDC_OBSERVE_ONLY,
            price_status=CANDIDATE_PRICE_STATUS_OK,
        ),
        _synthetic_candidate(
            index=6,
            token_mint="SmokeMintStale06",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_STALE,
        ),
        _synthetic_candidate(
            index=7,
            token_mint="SmokeMintMiss07",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_MISSING,
        ),
        _synthetic_candidate(
            index=8,
            token_mint="SmokeMintMal08",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_OK,
            malformed=True,
        ),
        _synthetic_candidate(
            index=9,
            token_mint="SmokeMintNotAllowed09",
            pair_quote_asset="SOL",
            pair_status=CANDIDATE_PAIR_STATUS_OK,
            price_status=CANDIDATE_PRICE_STATUS_OK,
            dispatch_allowed=False,
        ),
    )


# ---------------------------------------------------------------------------
# Stage 28.7 fake retry-friendly transport
# ---------------------------------------------------------------------------


# The default Stage 28.7 fake transport scripts a single
# transient network error followed by SENT_OK forever. Combined
# with a non-zero ``max_total_retries``, this exercises the Stage
# 28.6 bounded immediate retry path on the first dispatchable
# candidate. Tests that want a flat success path can inject a
# Stage28_6FakeTransport with ``scripted_outcomes=(SENT_OK,)``.
STAGE28_7_DEFAULT_SCRIPTED_OUTCOMES: tuple[str, ...] = (
    TRANSPORT_STATUS_NETWORK_ERROR,
    TRANSPORT_STATUS_SENT_OK,
)


def build_stage28_7_default_fake_transport() -> Stage28_6FakeTransport:
    """Construct a Stage 28.7 fake transport scripted to retry
    once and then succeed.
    """
    return Stage28_6FakeTransport(
        scripted_outcomes=STAGE28_7_DEFAULT_SCRIPTED_OUTCOMES,
    )


# ---------------------------------------------------------------------------
# Redaction scan
# ---------------------------------------------------------------------------


def scan_stage28_7_artifacts_for_redaction(
    *,
    output_dir: Path,
    artifact_basenames: Iterable[str] = STAGE28_7_ARTIFACT_BASENAMES,
) -> Stage28_7RedactionScanResult:
    """Scan every existing Stage 28.7 artifact under ``output_dir``
    for forbidden URL / secret / wallet / response-body substrings.

    Pure / deterministic. The function never echoes the offending
    file's body; only the closed-set substring label and the safe
    basename reach the result.

    Missing artifacts are silently skipped (a partial run may not
    have produced every artifact); the scan reports only the files
    it actually opened.
    """
    if not isinstance(output_dir, Path):
        return Stage28_7RedactionScanResult(
            schema_version=STAGE28_7_SCHEMA_VERSION,
            redaction_status=SMOKE_REDACTION_STATUS_NOT_SCANNED,
            files_scanned=(),
            offending_basenames=(),
            offending_substrings=(),
        )
    scanned: list[str] = []
    offending_basenames: list[str] = []
    offending_substrings: set[str] = set()
    for basename in sorted(set(artifact_basenames)):
        artifact_path = output_dir / basename
        if not artifact_path.exists() or not artifact_path.is_file():
            continue
        try:
            body = artifact_path.read_text(encoding="utf-8")
        except OSError:
            offending_basenames.append(basename)
            scanned.append(basename)
            continue
        scanned.append(basename)
        lowered = body.lower()
        local_hits: list[str] = []
        for needle in STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS:
            if needle.lower() in lowered:
                local_hits.append(needle)
        if local_hits:
            offending_basenames.append(basename)
            for hit in local_hits:
                offending_substrings.add(hit)
    if offending_basenames:
        status = SMOKE_REDACTION_STATUS_FAILED
    else:
        status = SMOKE_REDACTION_STATUS_SAFE
    return Stage28_7RedactionScanResult(
        schema_version=STAGE28_7_SCHEMA_VERSION,
        redaction_status=status,
        files_scanned=tuple(sorted(set(scanned))),
        offending_basenames=tuple(sorted(set(offending_basenames))),
        offending_substrings=tuple(sorted(offending_substrings)),
    )


# ---------------------------------------------------------------------------
# Smoke-summary writer
# ---------------------------------------------------------------------------


def write_stage28_7_smoke_summary(
    *,
    output_dir: Path,
    summary: Stage28_7SmokeSummary,
) -> Path:
    """Write the Stage 28.7 smoke summary JSON to ``output_dir``
    using canonical encoding.

    The writer wraps OSError as ``Stage28_7ArtifactWriteError``
    so the raw OSError text never reaches a caller.
    """
    if not isinstance(output_dir, Path):
        raise Stage28_7OutputDirError(
            reason=SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE,
        )
    target = output_dir / SMOKE_SUMMARY_ARTIFACT_BASENAME
    payload = canonical_smoke_summary_json(summary)
    try:
        target.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise Stage28_7ArtifactWriteError(
            operation="SMOKE_SUMMARY_WRITE",
            safe_basename=SMOKE_SUMMARY_ARTIFACT_BASENAME,
        ) from exc
    return target


def read_stage28_7_smoke_summary(
    output_dir: Path,
) -> Optional[dict]:
    """Replay the Stage 28.7 smoke summary at ``output_dir`` into a
    validated dict. Returns ``None`` when the artifact is absent.
    """
    if not isinstance(output_dir, Path):
        return None
    target = output_dir / SMOKE_SUMMARY_ARTIFACT_BASENAME
    if not target.exists() or not target.is_file():
        return None
    try:
        body = target.read_text(encoding="utf-8")
    except OSError:
        return None
    return json.loads(body)


def write_stage28_7_redaction_scan(
    *,
    output_dir: Path,
    result: Stage28_7RedactionScanResult,
) -> Path:
    """Write the Stage 28.7 redaction-scan artifact JSON."""
    if not isinstance(output_dir, Path):
        raise Stage28_7OutputDirError(
            reason=SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE,
        )
    target = output_dir / REDACTION_SCAN_ARTIFACT_BASENAME
    payload = canonical_redaction_scan_json(result)
    try:
        target.write_text(payload, encoding="utf-8")
    except OSError as exc:
        raise Stage28_7ArtifactWriteError(
            operation="REDACTION_SCAN_WRITE",
            safe_basename=REDACTION_SCAN_ARTIFACT_BASENAME,
        ) from exc
    return target


# ---------------------------------------------------------------------------
# Offline smoke entrypoint
# ---------------------------------------------------------------------------


DEFAULT_SMOKE_MAX_EVENTS: int = 64
DEFAULT_SMOKE_MAX_DISPATCHES: int = 32
DEFAULT_SMOKE_MAX_TOTAL_RETRIES: int = 3
DEFAULT_SMOKE_MAX_TICKS: int = 256
DEFAULT_SMOKE_HEARTBEAT_EVERY_N_EVENTS: int = 3


def _count_suppressions(run_summary: Stage28_6RunSummary) -> int:
    return (
        run_summary.duplicates_suppressed
        + run_summary.ambiguous_suppressed
        + run_summary.unknown_pair_suppressed
        + run_summary.disagree_pair_suppressed
        + run_summary.usdc_observe_only
        + run_summary.stale_price_suppressed
        + run_summary.missing_price_suppressed
        + run_summary.malformed_events
    )


def _count_heartbeats(output_dir: Path) -> int:
    target = output_dir / HEARTBEAT_ARTIFACT_BASENAME
    if not target.exists() or not target.is_file():
        return 0
    try:
        body = target.read_text(encoding="utf-8")
    except OSError:
        return 0
    if body == "":
        return 0
    return sum(1 for line in body.split("\n") if line)


def run_stage28_7_offline_smoke(
    *,
    output_dir: Path,
    smoke_id: str,
    run_id: str,
    session_id: str,
    candidates: Optional[
        Iterable[Stage28_6CandidateEvent]
    ] = None,
    transport: Optional[Stage28_6PrivateTransport] = None,
    max_events: int = DEFAULT_SMOKE_MAX_EVENTS,
    max_dispatches: int = DEFAULT_SMOKE_MAX_DISPATCHES,
    max_total_retries: int = DEFAULT_SMOKE_MAX_TOTAL_RETRIES,
    max_ticks: int = DEFAULT_SMOKE_MAX_TICKS,
    heartbeat_every_n_events: int = (
        DEFAULT_SMOKE_HEARTBEAT_EVERY_N_EVENTS
    ),
    perform_redaction_scan: bool = True,
) -> Stage28_7SmokeSummary:
    """Drive the Stage 28.7 deterministic offline smoke harness.

    Stage 28.7 is offline-only. The harness:

      * REFUSES to start without an explicitly injected
        ``output_dir`` (the directory must already exist).
      * Uses the Stage 28.6 bounded private session runner with
        the caller-injected (or default Stage 28.7) fake
        transport.
      * NEVER opens a network connection, NEVER reads the process
        environment, NEVER sleeps, NEVER schedules, NEVER spawns
        threads / async tasks / subprocesses.
      * NEVER performs a live Discord send; the
        ``live_send_attempted`` / ``live_send_count`` fields on
        the smoke summary are always ``False`` / ``0``.

    Returns the Stage 28.7 smoke summary; also writes the smoke
    summary JSON and (when ``perform_redaction_scan=True``) the
    Stage 28.7 redaction-scan artifact to ``output_dir``.
    """
    output_dir_safe_label = _validate_output_dir(output_dir)

    if candidates is None:
        candidate_tuple: Tuple[Stage28_6CandidateEvent, ...] = (
            build_stage28_7_synthetic_candidates()
        )
    else:
        candidate_tuple = tuple(candidates)

    if transport is None:
        injected_transport: Stage28_6PrivateTransport = (
            build_stage28_7_default_fake_transport()
        )
    else:
        injected_transport = transport

    config = build_runner_config(
        run_id=run_id,
        session_id=session_id,
        max_events=max_events,
        max_dispatches=max_dispatches,
        max_total_retries=max_total_retries,
        max_ticks=max_ticks,
        heartbeat_every_n_events=heartbeat_every_n_events,
        fail_closed_on_artifact_error=True,
        fail_closed_on_ledger_error=True,
        fail_closed_on_heartbeat_error=False,
    )

    ledger_path = output_dir / "stage28_7_dispatch_ledger.jsonl"
    heartbeat_path = output_dir / HEARTBEAT_ARTIFACT_BASENAME
    snapshot_path = output_dir / HEALTH_SNAPSHOT_ARTIFACT_BASENAME
    summary_path = output_dir / FINAL_SUMMARY_ARTIFACT_BASENAME

    runner = Stage28_6BoundedPrivateSessionRunner(
        config=config,
        transport=injected_transport,
        ledger_path=ledger_path,
        heartbeat_path=heartbeat_path,
        snapshot_path=snapshot_path,
        summary_path=summary_path,
    )
    run_summary: Stage28_6RunSummary = runner.run(candidate_tuple)

    heartbeat_count = _count_heartbeats(output_dir)

    redaction_basename: str = ""
    redaction_status: str = SMOKE_REDACTION_STATUS_NOT_SCANNED
    if perform_redaction_scan:
        # Scan the artifacts that exist before the smoke summary
        # / redaction scan are written so the scan covers the
        # runner-produced artifacts.
        runner_artifacts: tuple[str, ...] = (
            HEARTBEAT_ARTIFACT_BASENAME,
            HEALTH_SNAPSHOT_ARTIFACT_BASENAME,
            FINAL_SUMMARY_ARTIFACT_BASENAME,
        )
        scan_result = scan_stage28_7_artifacts_for_redaction(
            output_dir=output_dir,
            artifact_basenames=runner_artifacts,
        )
        write_stage28_7_redaction_scan(
            output_dir=output_dir,
            result=scan_result,
        )
        redaction_basename = REDACTION_SCAN_ARTIFACT_BASENAME
        redaction_status = scan_result.redaction_status

    if redaction_status == SMOKE_REDACTION_STATUS_FAILED:
        smoke_status = SMOKE_STATUS_REFUSED
        safe_reason_code = (
            SMOKE_SAFE_REASON_CODE_REDACTION_FAILED
        )
    elif (
        run_summary.ledger_failures > 0
        or run_summary.artifact_failures > 0
    ):
        smoke_status = SMOKE_STATUS_DEGRADED
        safe_reason_code = SMOKE_SAFE_REASON_CODE_DEGRADED
    elif run_summary.transport_failures > 0 and (
        run_summary.dispatch_failure > 0
    ):
        smoke_status = SMOKE_STATUS_DEGRADED
        safe_reason_code = SMOKE_SAFE_REASON_CODE_DEGRADED
    else:
        smoke_status = SMOKE_STATUS_OK
        safe_reason_code = SMOKE_SAFE_REASON_CODE_OK

    summary = Stage28_7SmokeSummary(
        schema_version=STAGE28_7_SCHEMA_VERSION,
        smoke_status=smoke_status,
        run_id=run_id,
        session_id=session_id,
        smoke_id=smoke_id,
        output_dir_safe_label=output_dir_safe_label,
        heartbeat_artifact_basename=HEARTBEAT_ARTIFACT_BASENAME,
        health_snapshot_artifact_basename=(
            HEALTH_SNAPSHOT_ARTIFACT_BASENAME
        ),
        final_summary_artifact_basename=(
            FINAL_SUMMARY_ARTIFACT_BASENAME
        ),
        smoke_summary_artifact_basename=(
            SMOKE_SUMMARY_ARTIFACT_BASENAME
        ),
        redaction_scan_artifact_basename=redaction_basename,
        offline_candidate_count=len(candidate_tuple),
        events_seen=run_summary.events_seen,
        candidates_seen=run_summary.candidates_seen,
        dispatch_attempts=run_summary.dispatch_attempts,
        dispatch_success=run_summary.dispatch_success,
        dispatch_failure=run_summary.dispatch_failure,
        retries_attempted=run_summary.retries_attempted,
        duplicate_suppressed=run_summary.duplicates_suppressed,
        ambiguous_suppressed=run_summary.ambiguous_suppressed,
        suppressed_count=_count_suppressions(run_summary),
        heartbeat_count=heartbeat_count,
        stop_reason=run_summary.stop_reason,
        final_health_status=run_summary.final_health_status,
        redaction_status=redaction_status,
        live_send_attempted=False,
        live_send_count=0,
        safe_reason_code=safe_reason_code,
    )

    write_stage28_7_smoke_summary(
        output_dir=output_dir,
        summary=summary,
    )

    return summary


__all__ = (
    # Version axes.
    "STAGE28_7_MINOR_VERSION",
    "STAGE28_7_SCHEMA_VERSION",
    "STAGE28_7_REDACTION_TOKEN",
    # Closed-set vocabularies.
    "SMOKE_STATUS_OK",
    "SMOKE_STATUS_DEGRADED",
    "SMOKE_STATUS_REFUSED",
    "SMOKE_STATUS_VALUES",
    "SMOKE_REDACTION_STATUS_SAFE",
    "SMOKE_REDACTION_STATUS_FAILED",
    "SMOKE_REDACTION_STATUS_NOT_SCANNED",
    "SMOKE_REDACTION_STATUS_VALUES",
    "SMOKE_SAFE_REASON_CODE_OK",
    "SMOKE_SAFE_REASON_CODE_DEGRADED",
    "SMOKE_SAFE_REASON_CODE_REDACTION_FAILED",
    "SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_MISSING",
    "SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_NOT_DIR",
    "SMOKE_SAFE_REASON_CODE_OUTPUT_DIR_UNSAFE",
    "SMOKE_SAFE_REASON_CODE_ARTIFACT_WRITE_FAILED",
    "SMOKE_SAFE_REASON_CODE_VALUES",
    # Artifact basenames.
    "HEARTBEAT_ARTIFACT_BASENAME",
    "HEALTH_SNAPSHOT_ARTIFACT_BASENAME",
    "FINAL_SUMMARY_ARTIFACT_BASENAME",
    "SMOKE_SUMMARY_ARTIFACT_BASENAME",
    "REDACTION_SCAN_ARTIFACT_BASENAME",
    "STAGE28_7_ARTIFACT_BASENAMES",
    # Forbidden substring vocabulary.
    "STAGE28_7_FORBIDDEN_ARTIFACT_SUBSTRINGS",
    # Field-name vocabularies.
    "STAGE28_7_SMOKE_SUMMARY_FIELD_NAMES",
    "STAGE28_7_REDACTION_SCAN_FIELD_NAMES",
    # Records.
    "Stage28_7SmokeSummary",
    "Stage28_7RedactionScanResult",
    # Exceptions.
    "Stage28_7SmokeHarnessError",
    "Stage28_7OutputDirError",
    "Stage28_7ArtifactWriteError",
    # Builders.
    "build_stage28_7_synthetic_candidates",
    "build_stage28_7_default_fake_transport",
    # Scan + IO.
    "scan_stage28_7_artifacts_for_redaction",
    "write_stage28_7_smoke_summary",
    "read_stage28_7_smoke_summary",
    "write_stage28_7_redaction_scan",
    "smoke_summary_to_dict",
    "redaction_scan_to_dict",
    "canonical_smoke_summary_json",
    "canonical_redaction_scan_json",
    # Smoke entrypoint.
    "run_stage28_7_offline_smoke",
    # Default budgets.
    "DEFAULT_SMOKE_MAX_EVENTS",
    "DEFAULT_SMOKE_MAX_DISPATCHES",
    "DEFAULT_SMOKE_MAX_TOTAL_RETRIES",
    "DEFAULT_SMOKE_MAX_TICKS",
    "DEFAULT_SMOKE_HEARTBEAT_EVERY_N_EVENTS",
    "STAGE28_7_DEFAULT_SCRIPTED_OUTCOMES",
)
