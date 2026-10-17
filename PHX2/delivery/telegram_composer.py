"""Deterministic Phoenix Telegram HTML composer.

The composer renders ONLY operator-facing conclusions.  Every metric field
crosses an explicit presentation boundary (`classify_operator_display`)
before it can appear in the body: a field is ``AVAILABLE`` (renders),
``UNAVAILABLE`` (renders the ``—`` marker or omits its line),
``NOT_APPLICABLE`` (no approved rule / disabled subsystem — omitted), or
``HIDDEN_INTERNAL`` (the value still carried an internal fallback pattern
and is suppressed).  The boundary is structural — it pattern-matches
internal enum/reason shapes instead of relying on a known-string
denylist — so a raw fallback value nested inside any field can never leak
into Telegram.  Unavailable evidence NEVER renders as an authentic zero;
the exact internal values and reasons stay on the artifact surface
(``field_reason_codes`` + the compose artifact).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape, unescape
import re
from typing import Dict, List, Mapping, Optional, Tuple


TELEGRAM_INTERNAL_MAX_CHARACTERS = 3900
_HTML_TAG_RE = re.compile(r"</?(?:b|code)>")

#: Closed sets for the evidence-coverage disclosure (2026-07-27 remediation).
#: ``COMPLETE_LIVE`` may only be claimed for a candidate whose migration was
#: observed live; a restart-backfill admission has evidence only since its
#: admission and must say so instead of presenting an observed-since-admission
#: maximum as the complete post-migration ATH.
#: ``HELIUS_LIVE`` is the stable rendering token for the LIVE_HELIUS
#: discovery provenance — an equal-authority live source, so it may claim
#: ``COMPLETE_LIVE`` coverage exactly like ``LIVE``.
#: ``COMPLETE_HYDRATED`` (2026-07-30) is a restart-backfill admission whose
#: migration-anchored OHLCV history has been fetched to completion and
#: verified: its maximum IS the complete post-migration ATH even though PHX2
#: admitted it late, so it labels the value honestly instead of "Obs ATH".
#: The tokens are re-exported from the shared send-path contract so the
#: renderer and the compose gate can never drift apart.
DISCOVERY_PROVENANCE_TOKENS = (
    "LIVE", "HELIUS_LIVE", "DEXSCREENER_RESTART_BACKFILL", "MERGED",
    "UNKNOWN")
from PHX2.models.ath_coverage import (  # noqa: E402
    ATH_COVERAGE_COMPLETE_HYDRATED,
    ATH_COVERAGE_COMPLETE_LIVE,
    ATH_COVERAGE_PARTIAL_SINCE_ADMISSION,
    ATH_COVERAGE_TOKENS,
    ATH_COVERAGE_UNKNOWN,
    ath_coverage_is_complete,
)


class TelegramMessageTooLong(ValueError):
    def __init__(self) -> None:
        self.reason = "MESSAGE_TOO_LONG"
        super().__init__(self.reason)


@dataclass(frozen=True)
class BuilderReadStatement:
    text: str
    reason_codes: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("BUILDER_STATEMENT_TEXT_REQUIRED")
        if not self.reason_codes or any(
            not isinstance(reason, str) or not reason.strip()
            for reason in self.reason_codes
        ):
            raise ValueError("BUILDER_STATEMENT_REASON_CODES_REQUIRED")


#: Ante shape placeholders that must never render in the operator body while
#: no approved deterministic Shape rule exists.  The reason codes stay in
#: ``field_reason_codes`` (artifact surface) unchanged.
ANTE_SHAPE_HIDDEN_VALUES = ("NO APPROVED SHAPE RULE", "INSUFFICIENT SAMPLE")
#: Operator display for a field whose canonical evidence is unavailable.
FIELD_UNAVAILABLE_DISPLAY = "—"

# ---- presentation boundary -------------------------------------------------

FIELD_AVAILABLE = "AVAILABLE"
FIELD_UNAVAILABLE = "UNAVAILABLE"
FIELD_NOT_APPLICABLE = "NOT_APPLICABLE"
FIELD_HIDDEN_INTERNAL = "HIDDEN_INTERNAL"
FIELD_PRESENTATION_STATUSES = (
    FIELD_AVAILABLE,
    FIELD_UNAVAILABLE,
    FIELD_NOT_APPLICABLE,
    FIELD_HIDDEN_INTERNAL,
)

#: Structural patterns of internal fallback values.  Approved operator text
#: never matches any of them: it has no bare ``UNKNOWN`` token, no
#: snake_case/SNAKE_CASE enum identifiers, and no run of three-plus
#: consecutive ALL-CAPS words (``SHADOW BLOCK`` is two and stays approved).
_INTERNAL_UNKNOWN_RE = re.compile(r"\bUNKNOWN\b")
_INTERNAL_ENUM_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:_[A-Za-z0-9]+)+\b")
_INTERNAL_CAPS_PHRASE_RE = re.compile(
    r"\b[A-Z][A-Z0-9]{1,}(?:\s+[A-Z][A-Z0-9]{1,}){2,}\b")


def display_value_is_operator_safe(value: str) -> bool:
    """True iff a display value carries no internal fallback pattern."""

    if _INTERNAL_UNKNOWN_RE.search(value):
        return False
    if _INTERNAL_ENUM_RE.search(value):
        return False
    if _INTERNAL_CAPS_PHRASE_RE.search(value):
        return False
    return True


def classify_operator_display(value: object) -> Tuple[str, str]:
    """Presentation boundary: ``(status, safe_display)`` for one field value.

    Empty / marker values classify ``UNAVAILABLE``; a value that still
    carries an internal fallback pattern classifies ``HIDDEN_INTERNAL`` and
    is suppressed (the raw value survives only on the artifact surface);
    everything else is ``AVAILABLE`` verbatim.
    """

    if not isinstance(value, str) or not value.strip():
        return FIELD_UNAVAILABLE, ""
    text = value.strip()
    if text == FIELD_UNAVAILABLE_DISPLAY:
        return FIELD_UNAVAILABLE, ""
    if not display_value_is_operator_safe(text):
        return FIELD_HIDDEN_INTERNAL, ""
    return FIELD_AVAILABLE, text


@dataclass(frozen=True)
class TelegramPingData:
    token_mint: str
    token_identity: str
    token_metadata_source: str
    age_minutes: int
    age_display: str
    tier: int
    market_cap: str
    post_migration_ath: str
    migration_market_cap: str
    floor: str
    volume: str
    liquidity: str
    quote_side_liquidity: str
    liquidity_basis: str
    liquidity_quality: str
    fee_gate_label: str
    fee_gate_score: str
    lp_integrity: str
    composite_verdict: str
    bribes_amm_pct: str
    creator_pct: str
    bribes_per_tx_lamports: str
    structure_read: str
    ante_last20_median: str
    ante_last20_p25: str
    ante_last20_p75: str
    ante_5m_median: str
    ante_5m_sample_count: str
    base_fee_coverage: str
    ante_last20_width: str
    ante_5m_width: str
    priority_fee_median_lamports: str
    priority_fee_sample_count: str
    shape_5m: str
    shape_5m_rule: str
    shape_last20: str
    shape_last20_rule: str
    #: Approved operator sentences only; empty means the section is omitted
    #: (the no-match reason stays in ``field_reason_codes``).
    builder_read: Tuple[BuilderReadStatement, ...] = ()
    #: Pre-formatted observe-only all-time Global Fees amount ("14.8 SOL"),
    #: optionally suffixed with the conclusive v1 support label
    #: ("14.8 SOL (Manipulated)").  Empty means the entire line (and its
    #: surrounding blank line) is omitted; the internal unavailability reason
    #: stays on the artifact surface only.
    global_fees_display: str = ""
    #: Operator-readable risk line ("Medium — LP falling").  Empty means the
    #: line is omitted from the body; the raw label/reasons stay in the
    #: compose artifact's source proofs.
    risk_warning: str = ""
    field_reason_codes: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    #: Observe-only Global Fee Support v1 artifact block (never rendered
    #: beyond the display suffix already folded into
    #: ``global_fees_display``).
    global_fee_support: Mapping[str, object] = field(default_factory=dict)
    #: Concise operator phrase for the compact SHADOW BLOCK policy line,
    #: chosen from the approved structured shadow reason codes.
    policy_reason_display: str = ""
    discovery_provenance: str = "LIVE"
    ath_coverage: str = ATH_COVERAGE_COMPLETE_LIVE
    phx1_structural_policy_mode: str = "ENFORCE"
    original_phx1_structural_verdict: str = "PASS"
    effective_phx1_policy_verdict: str = "PASS"
    shadow_warning_reasons: Tuple[str, ...] = ()
    organicity_status: str = "UNVERIFIED"
    manual_review_required: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.token_mint, str) or not self.token_mint.strip():
            raise ValueError("TOKEN_MINT_REQUIRED")
        if not isinstance(self.token_identity, str) \
                or not self.token_identity.strip():
            raise ValueError("TOKEN_IDENTITY_REQUIRED")
        if not isinstance(self.token_metadata_source, str) \
                or not self.token_metadata_source.strip():
            raise ValueError("TOKEN_METADATA_SOURCE_REQUIRED")
        if isinstance(self.age_minutes, bool) or not isinstance(self.age_minutes, int) \
                or self.age_minutes < 0:
            raise ValueError("AGE_MINUTES_INVALID")
        if not isinstance(self.age_display, str) or not self.age_display.strip():
            raise ValueError("AGE_DISPLAY_REQUIRED")
        if self.tier not in (1, 2, 3):
            raise ValueError("TIER_INVALID")
        if not isinstance(self.global_fees_display, str):
            raise ValueError("GLOBAL_FEES_DISPLAY_INVALID")
        if self.discovery_provenance not in DISCOVERY_PROVENANCE_TOKENS:
            raise ValueError("DISCOVERY_PROVENANCE_INVALID")
        if self.ath_coverage not in ATH_COVERAGE_TOKENS:
            raise ValueError("ATH_COVERAGE_INVALID")
        if self.ath_coverage == ATH_COVERAGE_COMPLETE_LIVE \
                and self.discovery_provenance not in (
                    "LIVE", "HELIUS_LIVE", "MERGED"):
            # A backfill-admitted candidate can never claim LIVE coverage; it
            # proves completeness through verified hydration instead.
            raise ValueError("ATH_COVERAGE_PROOF_INCONSISTENT")
        if self.ath_coverage == ATH_COVERAGE_COMPLETE_HYDRATED \
                and self.discovery_provenance != (
                    "DEXSCREENER_RESTART_BACKFILL"):
            raise ValueError("ATH_COVERAGE_PROOF_INCONSISTENT")
        if self.phx1_structural_policy_mode not in ("ENFORCE", "SHADOW"):
            raise ValueError("PHX1_STRUCTURAL_POLICY_INVALID")
        if self.original_phx1_structural_verdict not in ("PASS", "HARD_BLOCK"):
            raise ValueError("PHX1_STRUCTURAL_VERDICT_INVALID")
        if self.effective_phx1_policy_verdict not in (
            "PASS", "HARD_BLOCK", "ALLOW_WITH_SHADOW_WARNING"
        ):
            raise ValueError("PHX1_EFFECTIVE_VERDICT_INVALID")
        if any(not isinstance(reason, str) or not reason.strip()
               for reason in self.shadow_warning_reasons):
            raise ValueError("PHX1_SHADOW_REASON_INVALID")
        if self.effective_phx1_policy_verdict == "ALLOW_WITH_SHADOW_WARNING":
            if (
                self.phx1_structural_policy_mode != "SHADOW"
                or self.original_phx1_structural_verdict != "HARD_BLOCK"
                or not self.shadow_warning_reasons
                or not self.manual_review_required
                or self.organicity_status != "UNVERIFIED"
            ):
                raise ValueError("PHX1_SHADOW_WARNING_PROOF_INCONSISTENT")
        elif self.original_phx1_structural_verdict == "PASS" and (
            self.effective_phx1_policy_verdict != "PASS"
            or self.shadow_warning_reasons
            or self.manual_review_required
        ):
            raise ValueError("PHX1_PASS_PROOF_INCONSISTENT")


@dataclass(frozen=True)
class TelegramComposeResult:
    text: str
    rendered_character_count: int
    builder_reason_map: Mapping[str, Tuple[str, ...]]
    field_reason_codes: Mapping[str, Tuple[str, ...]]
    #: Closed-set presentation status per operator-surface field
    #: (AVAILABLE / UNAVAILABLE / NOT_APPLICABLE / HIDDEN_INTERNAL).
    field_presentation: Mapping[str, str] = field(default_factory=dict)


def _e(value: object) -> str:
    return escape(str(value), quote=True)


def rendered_character_count(message: str) -> int:
    """Count the message after the two supported HTML entity tags are parsed."""

    # Conservative UTF-16 count also bounds emoji/non-BMP captions correctly.
    return len(unescape(_HTML_TAG_RE.sub("", message)).encode("utf-16-le")) // 2


class _PresentationBoundary:
    """Field classifier that records one closed-set status per field."""

    def __init__(self) -> None:
        self.statuses: Dict[str, str] = {}

    def dash(self, name: str, value: object) -> str:
        """Classify a keep-the-line field; non-AVAILABLE renders ``—``."""

        status, display = classify_operator_display(value)
        self.statuses[name] = status
        return display if status == FIELD_AVAILABLE \
            else FIELD_UNAVAILABLE_DISPLAY

    def optional(self, name: str, value: object) -> Optional[str]:
        """Classify an omit-the-line field; non-AVAILABLE returns ``None``."""

        status, display = classify_operator_display(value)
        self.statuses[name] = status
        return display if status == FIELD_AVAILABLE else None

    def not_applicable(self, name: str) -> None:
        self.statuses[name] = FIELD_NOT_APPLICABLE


def compose_telegram_ping(data: TelegramPingData) -> TelegramComposeResult:
    """Render the operator decision surface.

    Section order: title/mint, State, Global Fees (when valid), Structure,
    Ante (only when at least one meaningful group is valid), Builder Read
    (only when an approved sentence exists).  Participation renders NOWHERE —
    it is artifact-only telemetry.  Internal reason codes, coverage enums,
    provenance schema tokens, disabled-subsystem rows, and unapproved
    classifier placeholders stay OUT of the body; every metric crosses the
    presentation boundary, so an unavailable canonical field renders as ``—``
    or is omitted — never as its internal failure reason and never as a
    synthetic zero.
    """

    boundary = _PresentationBoundary()

    # ---- State ---------------------------------------------------------
    # "Post-mig ATH" is claimed only when the coverage token PROVES the whole
    # post-migration window (live observation, or verified hydration of a
    # restart-backfill admission).  Anything else stays "Obs ATH".
    ath_label = ("Post-mig ATH" if ath_coverage_is_complete(data.ath_coverage)
                 else "Obs ATH")
    market_cap = boundary.dash("market_cap", data.market_cap)
    post_migration_ath = boundary.dash(
        "post_migration_ath", data.post_migration_ath)
    migration_market_cap = boundary.dash(
        "migration_market_cap", data.migration_market_cap)
    floor = boundary.dash("floor", data.floor)
    volume = boundary.dash("volume", data.volume)
    liquidity = boundary.dash("liquidity", data.liquidity)
    state_lines = [
        "<b>🧠 State</b>",
        (f"• MC: {_e(market_cap)} | {ath_label}: "
         f"{_e(post_migration_ath)} | Mig: {_e(migration_market_cap)}"),
        (f"• Floor: {_e(floor)} | Age: {_e(data.age_display)} | "
         f"Vol 5m: {_e(volume)}"),
        f"• LP: {_e(liquidity)}",
    ]
    # The rendered body must stay clean of the provider-name needle the
    # runtime redaction scanner bans in free-text artifacts; the coverage
    # disclosure is provider-neutral while the schema token stays canonical
    # in the structured artifact fields.
    if data.ath_coverage == ATH_COVERAGE_PARTIAL_SINCE_ADMISSION:
        state_lines.append("• Coverage: Partial (restart backfill)")
    elif data.ath_coverage == ATH_COVERAGE_COMPLETE_HYDRATED:
        state_lines.append("• Coverage: Complete (restart backfill hydrated)")
    elif data.ath_coverage == ATH_COVERAGE_UNKNOWN:
        state_lines.append("• Coverage: Unknown")

    # ---- Global Fees (observe-only) ------------------------------------
    global_fees = boundary.optional("global_fees", data.global_fees_display)

    # ---- Structure -----------------------------------------------------
    fee_gate_label = boundary.optional("fee_gate", data.fee_gate_label)
    _score_status, fee_gate_score = classify_operator_display(
        data.fee_gate_score)
    if fee_gate_label is not None and fee_gate_score:
        fee_gate_display = f"{_e(fee_gate_label)} ({_e(fee_gate_score)})"
    else:
        # Label and score share one evidence status: either both render or
        # the line keeps the unavailable marker.
        boundary.statuses["fee_gate"] = (
            boundary.statuses["fee_gate"]
            if boundary.statuses["fee_gate"] != FIELD_AVAILABLE
            else _score_status)
        fee_gate_display = FIELD_UNAVAILABLE_DISPLAY
    structure_lines = ["<b>🛑 Structure</b>",
                       f"• Fee Gate: {fee_gate_display}"]
    risk = boundary.optional("risk", data.risk_warning)
    if risk is not None:
        structure_lines.append(f"• Risk: {_e(risk)}")
    bribes_amm = boundary.optional("fee_breakdown", data.bribes_amm_pct)
    _creator_status, creator_pct = classify_operator_display(data.creator_pct)
    _bribes_status, bribes_per_tx = classify_operator_display(
        data.bribes_per_tx_lamports)
    if bribes_amm is not None and creator_pct and bribes_per_tx:
        # The three shares carry one shared evidence window: they render
        # together or the whole line is omitted (never synthetic zeroes).
        structure_lines.append(
            f"• Bribes/AMM: {_e(bribes_amm)} | Creator: "
            f"{_e(creator_pct)} | Bribes/tx: {_e(bribes_per_tx)} lamports")
    elif boundary.statuses["fee_breakdown"] == FIELD_AVAILABLE:
        boundary.statuses["fee_breakdown"] = (
            _creator_status if not creator_pct else _bribes_status)
    structure_read = boundary.optional("structure_read", data.structure_read)
    if structure_read is not None:
        structure_lines.append(f"• Read: {_e(structure_read)}")
    if data.manual_review_required:
        _policy_status, policy_reason = classify_operator_display(
            data.policy_reason_display)
        boundary.statuses["policy"] = FIELD_AVAILABLE
        structure_lines.append(
            "• Policy: SHADOW BLOCK — "
            f"{_e(policy_reason or 'structural shadow block')}")
    else:
        boundary.not_applicable("policy")

    # ---- Ante (observe-only, meaningful groups only) -------------------
    ante_lines: List[str] = []
    last20_median = boundary.optional("ante_last20", data.ante_last20_median)
    _p25_status, last20_p25 = classify_operator_display(data.ante_last20_p25)
    _p75_status, last20_p75 = classify_operator_display(data.ante_last20_p75)
    if last20_median is not None and last20_p25 and last20_p75:
        ante_lines.append(
            f"• Median last-20sw: {_e(last20_median)} SOL | p25/p75: "
            f"{_e(last20_p25)} / {_e(last20_p75)}")
    elif boundary.statuses["ante_last20"] == FIELD_AVAILABLE:
        boundary.statuses["ante_last20"] = (
            _p25_status if not last20_p25 else _p75_status)
    ante_5m_median = boundary.optional("ante_5m", data.ante_5m_median)
    _count_status, ante_5m_count = classify_operator_display(
        data.ante_5m_sample_count)
    if ante_5m_median is not None and ante_5m_count:
        coverage_status, base_coverage = classify_operator_display(
            data.base_fee_coverage)
        boundary.statuses["base_fee_coverage"] = coverage_status
        ante_lines.append(
            f"• Median 5m: {_e(ante_5m_median)} SOL "
            f"(n={_e(ante_5m_count)}) | base-fee cov: "
            f"{_e(base_coverage or FIELD_UNAVAILABLE_DISPLAY)}")
    else:
        if boundary.statuses["ante_5m"] == FIELD_AVAILABLE:
            boundary.statuses["ante_5m"] = _count_status
        boundary.statuses["base_fee_coverage"] = FIELD_UNAVAILABLE
    width20_status, width20 = classify_operator_display(data.ante_last20_width)
    width5_status, width5 = classify_operator_display(data.ante_5m_width)
    width_segments = []
    if width20:
        width_segments.append(f"last20 {_e(width20)}×")
    if width5:
        width_segments.append(f"5m {_e(width5)}×")
    boundary.statuses["ante_widths"] = (
        FIELD_AVAILABLE if width_segments
        else (width20_status if width20_status != FIELD_AVAILABLE
              else width5_status))
    if width_segments:
        ante_lines.append("• Width: " + " | ".join(width_segments))
    priority_median = boundary.optional(
        "priority_fee", data.priority_fee_median_lamports)
    _priority_count_status, priority_count = classify_operator_display(
        data.priority_fee_sample_count)
    if priority_median is not None and priority_count:
        ante_lines.append(
            f"⛽️ Priority Fee: {_e(priority_median)} lam "
            f"(n={_e(priority_count)})")
    elif boundary.statuses["priority_fee"] == FIELD_AVAILABLE:
        boundary.statuses["priority_fee"] = _priority_count_status
    # Shape lines render ONLY for an approved deterministic rule output; the
    # placeholder values are NOT_APPLICABLE while no approved rule exists.
    for name, shape, rule in (
        ("shape_5m", data.shape_5m, data.shape_5m_rule),
        ("shape_last20", data.shape_last20, data.shape_last20_rule),
    ):
        if shape in ANTE_SHAPE_HIDDEN_VALUES:
            boundary.not_applicable(name)
            continue
        shape_display = boundary.optional(name, shape)
        _rule_status, rule_display = classify_operator_display(rule)
        if shape_display is not None and rule_display and ante_lines:
            label = "Shape (5m)" if name == "shape_5m" else "Shape (20sw)"
            ante_lines.append(
                f"• {label}: {_e(shape_display)} "
                f"(rule {_e(rule_display)})")

    # ---- Builder Read --------------------------------------------------
    builder_lines: List[str] = []
    for statement in data.builder_read:
        status, display = classify_operator_display(statement.text)
        if status == FIELD_AVAILABLE:
            builder_lines.append(f"• {_e(display)}")
    boundary.statuses["builder_read"] = (
        FIELD_AVAILABLE if builder_lines else FIELD_UNAVAILABLE)

    # ---- assembly ------------------------------------------------------
    sections: List[List[str]] = [
        [
            (f"<b>🔥 PHOENIX — {_e(data.token_identity)} "
             f"[Tier {_e(data.tier)}]</b>"),
            f"<code>{_e(data.token_mint)}</code>",
        ],
        state_lines,
    ]
    if global_fees is not None:
        sections.append([f"💸 Global Fees: {_e(global_fees)}"])
    sections.append(structure_lines)
    if ante_lines:
        sections.append(["<b>🎲 Ante (observe-only)</b>", *ante_lines])
    if builder_lines:
        sections.append(["<b>🏗️ Builder Read</b>", *builder_lines])
    message = "\n\n".join("\n".join(section) for section in sections)
    count = rendered_character_count(message)
    if count > TELEGRAM_INTERNAL_MAX_CHARACTERS:
        raise TelegramMessageTooLong()
    return TelegramComposeResult(
        text=message,
        rendered_character_count=count,
        builder_reason_map={
            statement.text: tuple(statement.reason_codes)
            for statement in data.builder_read
        },
        field_reason_codes=dict(data.field_reason_codes),
        field_presentation=dict(boundary.statuses),
    )


__all__ = (
    "TELEGRAM_INTERNAL_MAX_CHARACTERS",
    "ANTE_SHAPE_HIDDEN_VALUES",
    "FIELD_UNAVAILABLE_DISPLAY",
    "FIELD_AVAILABLE",
    "FIELD_UNAVAILABLE",
    "FIELD_NOT_APPLICABLE",
    "FIELD_HIDDEN_INTERNAL",
    "FIELD_PRESENTATION_STATUSES",
    "ATH_COVERAGE_COMPLETE_LIVE",
    "ATH_COVERAGE_COMPLETE_HYDRATED",
    "ATH_COVERAGE_PARTIAL_SINCE_ADMISSION",
    "ATH_COVERAGE_UNKNOWN",
    "ATH_COVERAGE_TOKENS",
    "DISCOVERY_PROVENANCE_TOKENS",
    "BuilderReadStatement",
    "TelegramComposeResult",
    "TelegramMessageTooLong",
    "TelegramPingData",
    "classify_operator_display",
    "display_value_is_operator_safe",
    "compose_telegram_ping",
    "rendered_character_count",
)
