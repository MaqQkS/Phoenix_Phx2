// Phoenix — Calibration page (manual labeling workbench)
// Static mock data only. Research-only labels, no live writes.

// ─── Bin definitions ─────────────────────────────────────────────────
const CALIB_BINS = [
  { id: "UNLABELED",      label: "Unlabeled Pool",       tone: "info",     pool: true },
  { id: "GOLD",           label: "Gold Standard",        tone: "called",   icon: "★" },
  { id: "ORGANIC",        label: "Organic / Real",       tone: "ok",       icon: "✓" },
  { id: "BUNDLED",        label: "Bundled / Manufactured", tone: "ember",  icon: "◆" },
  { id: "WASHY",          label: "Washy / Suspicious",   tone: "warn",     icon: "~" },
  { id: "RUG",            label: "Scam / Rug",           tone: "bad",      icon: "☠" },
  { id: "LOW_QUALITY",    label: "Low Quality / Dead",   tone: "bad",      icon: "↓" },
  { id: "USDC_OBSERVE",   label: "USDC Observe-only",    tone: "watching", icon: "≈" },
  { id: "AMBIGUOUS",      label: "Ambiguous",            tone: "muted",    icon: "?" },
  { id: "NEEDS_REVIEW",   label: "Needs Review",         tone: "ember",    icon: "!" },
  { id: "EXCLUDE",        label: "Exclude / Censored",   tone: "muted",    icon: "∅" },
];

const CALIB_BIN_LOOKUP = Object.fromEntries(CALIB_BINS.map((b) => [b.id, b]));

// ─── Token data ──────────────────────────────────────────────────────
const CalibInitialTokens = [
  {
    id: "popcat", token: "POPCAT", tokenSub: "9xK3…vB2p", pair: "POPCAT / SOL", pairQuote: "SOL",
    decision: "WOULD_ALERT", reason: "T1_DRAWDOWN_CONFIRMED", outcome: "HIT",
    maxBounce: 82.4, maxDrawdown: -8.2, athReclaim: false,
    filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
    suggested: "SUGGEST_ORGANIC", confidence: "HIGH",
    evidence: "Clean T1 bounce, ATH confirmed, all filters pass.",
    note: "Clean pullback, ATH confirmed, fresh price, strong bounce after T1.",
    bin: "UNLABELED", age: "2h",
  },
  {
    id: "pnut", token: "PNUT", tokenSub: "3xVm…K7Lq", pair: "PNUT / SOL", pairQuote: "SOL",
    decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED", outcome: "HIT",
    maxBounce: 56.1, maxDrawdown: -4.4, athReclaim: false,
    filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
    suggested: "SUGGEST_ORGANIC", confidence: "HIGH",
    evidence: "T2 bounce confirmed +56% within 2h 14m.",
    note: "Organic momentum, no bundle signals, gold-eligible.",
    bin: "UNLABELED", age: "4h",
  },
  {
    id: "pepe", token: "PEPE", tokenSub: "5n4Q…aR2v", pair: "PEPE / SOL", pairQuote: "SOL",
    decision: "WOULD_ALERT", reason: "T1_DRAWDOWN_CONFIRMED", outcome: "RECLAIMED_ATH",
    maxBounce: 124.0, maxDrawdown: -2.1, athReclaim: true,
    filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
    suggested: "SUGGEST_ORGANIC", confidence: "HIGH",
    evidence: "Reclaimed prior ATH. Strongest possible reference example.",
    note: "Gold standard organic reference — reclaimed ATH after T1 alert.",
    bin: "GOLD", age: "6h",
  },
  {
    id: "goat", token: "GOAT", tokenSub: "X2pQ…4nMv", pair: "GOAT / SOL", pairQuote: "SOL",
    decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED", outcome: "MISS",
    maxBounce: 12.4, maxDrawdown: -68.0, athReclaim: false,
    filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
    suggested: "SUGGEST_REVIEW", confidence: "MEDIUM",
    evidence: "Phoenix would-alert but bounce stalled +12% then -68%.",
    note: "Possible structural failure — review for hidden bundle pattern.",
    bin: "UNLABELED", age: "8h", conflictType: "ALERT_DIED",
  },
  {
    id: "cheems", token: "CHEEMS", tokenSub: "Cq8N…vK3R", pair: "CHEEMS / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "BUNDLE_RISK", outcome: "SAVED_BY_SKIP",
    maxBounce: -8.0, maxDrawdown: -71.0, athReclaim: false,
    filters: "BUNDLE_RISK", filtersTone: "bad", dataQuality: "COMPLETE",
    suggested: "SUGGEST_BUNDLED", confidence: "HIGH",
    evidence: "Bundle risk 0.84 at decision, died -71% post-skip.",
    note: "Bundle risk present, died after migration, no meaningful recovery.",
    bin: "UNLABELED", age: "5m",
  },
  {
    id: "moodeng", token: "MOODENG", tokenSub: "9vRk…X2pN", pair: "MOODENG / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "LOW_LIQUIDITY", outcome: "SAVED_BY_SKIP",
    maxBounce: -3.2, maxDrawdown: -64.0, athReclaim: false,
    filters: "LIQ_DROP", filtersTone: "bad", dataQuality: "COMPLETE",
    suggested: "SUGGEST_WASHY", confidence: "MEDIUM",
    evidence: "Liquidity collapsing, washy volume pattern.",
    note: "Manufactured volume signals — washy bin candidate.",
    bin: "UNLABELED", age: "18s",
  },
  {
    id: "neiro", token: "NEIRO", tokenSub: "Vm8K…3pXr", pair: "NEIRO / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "LOW_LIQUIDITY", outcome: "SAVED_BY_SKIP",
    maxBounce: -5.1, maxDrawdown: -82.0, athReclaim: false,
    filters: "LOW_LIQ", filtersTone: "bad", dataQuality: "PARTIAL",
    suggested: "SUGGEST_BUNDLED", confidence: "MEDIUM",
    evidence: "Thin liquidity + concentrated holders → bundle suspicion.",
    note: "Likely bundled — review holder concentration further.",
    bin: "UNLABELED", age: "38m",
  },
  {
    id: "degen", token: "DEGEN", tokenSub: "2sNv…UqWk", pair: "DEGEN / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "DEAD_CHART_PATTERN", outcome: "DEAD",
    maxBounce: -12.0, maxDrawdown: -97.6, athReclaim: false,
    filters: "RUG_PATTERN", filtersTone: "bad", dataQuality: "COMPLETE",
    suggested: "SUGGEST_RUG", confidence: "HIGH",
    evidence: "Dead chart pattern, -97% confirmed. Textbook rug.",
    note: "Gold-eligible rug example — clean evidence, complete data.",
    bin: "UNLABELED", age: "12m",
  },
  {
    id: "bome", token: "BOME", tokenSub: "4nL2…XmQr", pair: "BOME / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "DEAD_CHART_PATTERN", outcome: "DEAD",
    maxBounce: -8.4, maxDrawdown: -95.0, athReclaim: false,
    filters: "RUG_PATTERN", filtersTone: "bad", dataQuality: "COMPLETE",
    suggested: "SUGGEST_RUG", confidence: "HIGH",
    evidence: "Confirmed rug pattern. Liquidity collapsed.",
    note: "Rug example — solid label candidate.",
    bin: "UNLABELED", age: "21m",
  },
  {
    id: "wif", token: "WIF", tokenSub: "EKp…1F2h", pair: "WIF / USDC", pairQuote: "USDC",
    decision: "OBSERVE_ONLY", reason: "USDC_PAIR_OBSERVE_ONLY", outcome: "PARTIAL",
    maxBounce: 31.2, maxDrawdown: -6.4, athReclaim: false,
    filters: "USDC_PAIR", filtersTone: "watching", dataQuality: "COMPLETE",
    suggested: "SUGGEST_REVIEW", confidence: "MEDIUM",
    evidence: "USDC pair uncalibrated — outcome not comparable.",
    note: "USDC pair; keep observe-only until separate calibration exists.",
    bin: "UNLABELED", age: "1h 50m", conflictType: "USDC_UNCALIBRATED",
  },
  {
    id: "useless", token: "USELESS", tokenSub: "Hk9Q…7vRt", pair: "USELESS / USDC", pairQuote: "USDC",
    decision: "OBSERVE_ONLY", reason: "USDC_PAIR_OBSERVE_ONLY", outcome: "LATER_CANDIDATE",
    maxBounce: 18.0, maxDrawdown: -3.1, athReclaim: false,
    filters: "USDC_PAIR", filtersTone: "watching", dataQuality: "COMPLETE",
    suggested: "SUGGEST_REVIEW", confidence: "MEDIUM",
    evidence: "USDC quote; later re-entered candidate queue.",
    note: "USDC pair, candidate behavior — review.",
    bin: "UNLABELED", age: "8m", conflictType: "USDC_UNCALIBRATED",
  },
  {
    id: "bonk", token: "BONK", tokenSub: "DezX…8mNq", pair: "BONK / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "ATH_UNKNOWN", outcome: "CENSORED",
    maxBounce: null, maxDrawdown: null, athReclaim: null,
    filters: "ATH_UNKNOWN", filtersTone: "warn", dataQuality: "MISSING_ATH",
    suggested: "SUGGEST_EXCLUDE", confidence: "HIGH",
    evidence: "ATH unknown — cannot trust drawdown.",
    note: "Exclude: ATH unknown, cannot measure drawdown truthfully.",
    bin: "UNLABELED", age: "1m", conflictType: "DATA_CENSORED",
  },
  {
    id: "cash", token: "CASH", tokenSub: "8vRm…2WkN", pair: "CASH / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "ATH_UNKNOWN", outcome: "CENSORED",
    maxBounce: null, maxDrawdown: null, athReclaim: null,
    filters: "ATH_UNKNOWN", filtersTone: "warn", dataQuality: "MISSING_ATH",
    suggested: "SUGGEST_EXCLUDE", confidence: "HIGH",
    evidence: "ATH unknown.",
    note: "Exclude — same reason as BONK.",
    bin: "UNLABELED", age: "3h 02m", conflictType: "DATA_CENSORED",
  },
  {
    id: "mog", token: "MOG", tokenSub: "Bx5p…RkLm", pair: "MOG / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "PRICE_STALE", outcome: "NO_DATA",
    maxBounce: null, maxDrawdown: null, athReclaim: null,
    filters: "PRICE_STALE", filtersTone: "warn", dataQuality: "STALE",
    suggested: "SUGGEST_EXCLUDE", confidence: "HIGH",
    evidence: "Price feed stale throughout the outcome window.",
    note: "Exclude — no reliable post-decision price.",
    bin: "UNLABELED", age: "2m", conflictType: "DATA_CENSORED",
  },
  {
    id: "bork", token: "BORK", tokenSub: "3kQv…6JrN", pair: "BORK / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "FILTER_INCOMPLETE", outcome: "CENSORED",
    maxBounce: null, maxDrawdown: null, athReclaim: null,
    filters: "FILTERS_INCOMPLETE", filtersTone: "warn", dataQuality: "FILTER_INCOMPLETE",
    suggested: "SUGGEST_EXCLUDE", confidence: "MEDIUM",
    evidence: "Filter set never completed.",
    note: "Exclude — incomplete filter context.",
    bin: "UNLABELED", age: "1h", conflictType: "DATA_CENSORED",
  },
  {
    id: "brett", token: "BRETT", tokenSub: "9pBn…2KqL", pair: "BRETT / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "BELOW_TIER_THRESHOLD", outcome: "MISSED_RUNNER",
    maxBounce: 147.0, maxDrawdown: -12.0, athReclaim: false,
    filters: "EVAL", filtersTone: "info", dataQuality: "COMPLETE",
    suggested: "SUGGEST_REVIEW", confidence: "LOW",
    evidence: "Skipped below tier threshold, ran +147% afterwards.",
    note: "Skip vs ran — review threshold calibration.",
    bin: "UNLABELED", age: "1h 14m", conflictType: "SKIP_RAN",
  },
  {
    id: "giga", token: "GIGA", tokenSub: "Lq2N…8rXm", pair: "GIGA / SOL", pairQuote: "SOL",
    decision: "SKIP", reason: "LOW_LIQUIDITY", outcome: "MISSED_RUNNER",
    maxBounce: 94.0, maxDrawdown: -8.0, athReclaim: false,
    filters: "LOW_LIQ", filtersTone: "bad", dataQuality: "COMPLETE",
    suggested: "SUGGEST_REVIEW", confidence: "LOW",
    evidence: "Existing label may be wrong — liquidity recovered post-decision.",
    note: "Existing MANUAL_LOW_QUALITY label may need revision.",
    bin: "LOW_QUALITY", age: "42m", conflictType: "LABEL_MISMATCH",
  },
  {
    id: "andy", token: "ANDY", tokenSub: "Hk4Q…2vRt", pair: "ANDY / SOL", pairQuote: "SOL",
    decision: "WATCH", reason: "BELOW_TIER_THRESHOLD", outcome: "LATER_ALERTED",
    maxBounce: 8.0, maxDrawdown: -52.0, athReclaim: false,
    filters: "EVAL", filtersTone: "info", dataQuality: "COMPLETE",
    suggested: "SUGGEST_ORGANIC", confidence: "MEDIUM",
    evidence: "Crossed threshold under WATCH, promoted to alert.",
    note: "Organic — graduated from WATCH to alert.",
    bin: "UNLABELED", age: "31m",
  },
  {
    id: "chill", token: "CHILL", tokenSub: "7Hp1…D9Mz", pair: "CHILL / SOL", pairQuote: "SOL",
    decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED", outcome: "PENDING",
    maxBounce: 4.2, maxDrawdown: -1.1, athReclaim: null,
    filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
    suggested: "SUGGEST_AMBIGUOUS", confidence: "LOW",
    evidence: "Outcome window still open.",
    note: "Wait for window to close before labeling.",
    bin: "UNLABELED", age: "14m",
  },
];

// ─── Conflict detection ──────────────────────────────────────────────
function detectConflict(t) {
  if (t.conflictType) return t.conflictType;
  if (t.decision === "SKIP" && t.outcome === "MISSED_RUNNER") return "SKIP_RAN";
  if (t.decision === "WOULD_ALERT" && (t.outcome === "MISS" || t.outcome === "DEAD")) return "ALERT_DIED";
  if (["CENSORED","NO_DATA"].includes(t.outcome)) return "DATA_CENSORED";
  if (t.pairQuote === "USDC") return "USDC_UNCALIBRATED";
  if (t.bin !== "UNLABELED" && t.bin !== "GOLD" && t.suggested.replace("SUGGEST_","") !== binToSuggest(t.bin)) return "LABEL_MISMATCH";
  return null;
}

// ─── Review status derivation ────────────────────────────────────────
function deriveReviewStatus(t) {
  if (t.reviewStatus) return t.reviewStatus;
  if (detectConflict(t) && t.confidence === "LOW") return "CONFLICT";
  if (t.bin === "EXCLUDE" || ["MISSING_ATH","STALE","FILTER_INCOMPLETE"].includes(t.dataQuality)) return "EXCLUDED";
  if (t.bin === "GOLD") return "REVIEWED";
  if (t.confidence === "MEDIUM" && t.suggested === "SUGGEST_REVIEW") return "NEEDS_MORE_DATA";
  if (t.bin === "UNLABELED" && t.confidence === "HIGH" && ["SUGGEST_ORGANIC","SUGGEST_RUG"].includes(t.suggested)) return "GOLD_CANDIDATE";
  if (t.bin === "UNLABELED") return "UNREVIEWED";
  return "REVIEWED";
}
const reviewStatusTone = {
  UNREVIEWED: "muted",
  REVIEWED: "ok",
  CONFLICT: "bad",
  NEEDS_MORE_DATA: "warn",
  GOLD_CANDIDATE: "called",
  EXCLUDED: "muted",
};
function ReviewStatusPill({ value }) {
  return <span className={"pill pill-" + (reviewStatusTone[value] || "muted") + " pill-dim"}>{value}</span>;
}
function binToSuggest(binId) {
  const map = {
    ORGANIC: "ORGANIC", BUNDLED: "BUNDLED", WASHY: "WASHY", RUG: "RUG",
    LOW_QUALITY: "REVIEW", USDC_OBSERVE: "REVIEW", AMBIGUOUS: "AMBIGUOUS",
    NEEDS_REVIEW: "REVIEW", EXCLUDE: "EXCLUDE", GOLD: "ORGANIC",
  };
  return map[binId] || "REVIEW";
}

// ─── Components ──────────────────────────────────────────────────────
const labelTone = {
  UNLABELED: "muted",
  MANUAL_ORGANIC: "ok",
  MANUAL_BUNDLED: "ember",
  MANUAL_WASHY: "warn",
  MANUAL_RUG: "bad",
  MANUAL_LOW_QUALITY: "bad",
  MANUAL_AMBIGUOUS: "muted",
  MANUAL_EXCLUDE: "muted",
  NEEDS_REVIEW: "ember",
  GOLD_REFERENCE: "called",
};
function currentLabelFor(bin) {
  return {
    UNLABELED: "UNLABELED",
    ORGANIC: "MANUAL_ORGANIC",
    BUNDLED: "MANUAL_BUNDLED",
    WASHY: "MANUAL_WASHY",
    RUG: "MANUAL_RUG",
    LOW_QUALITY: "MANUAL_LOW_QUALITY",
    USDC_OBSERVE: "MANUAL_LOW_QUALITY",
    AMBIGUOUS: "MANUAL_AMBIGUOUS",
    NEEDS_REVIEW: "NEEDS_REVIEW",
    EXCLUDE: "MANUAL_EXCLUDE",
    GOLD: "GOLD_REFERENCE",
  }[bin] || "UNLABELED";
}

function ConfidenceChip({ value }) {
  const tone = value === "HIGH" ? "ok" : value === "MEDIUM" ? "warn" : "bad";
  return <span className={"conf-chip conf-" + tone}>{value}</span>;
}

function TokenChip({ t, onClick, draggable, onDragStart, onDragEnd, isDragging }) {
  return (
    <div
      className={"tok-chip" + (isDragging ? " tok-chip-dragging" : "")}
      onClick={(e) => { e.stopPropagation(); onClick && onClick(); }}
      draggable={draggable}
      onDragStart={onDragStart}
      onDragEnd={onDragEnd}
    >
      <div className="tok-chip-l">
        <span className="tok-sym">{t.token}</span>
        <span className="mono tok-chip-quote">/ {t.pairQuote}</span>
      </div>
      <div className="tok-chip-r">
        <span className={"tok-chip-out tok-chip-out-" + (outcomeTone[t.outcome] || "muted")}>
          {outcomeIcon[t.outcome] || "·"}
        </span>
        <ConfidenceChip value={t.confidence} />
      </div>
    </div>
  );
}

// ─── Evidence Drawer ─────────────────────────────────────────────────
function EvidenceDrawer({ token, onClose, onMove }) {
  if (!token) return null;
  const conflict = detectConflict(token);
  return (
    <>
      <div className="cd-scrim" onClick={onClose} />
      <aside className="cd-drawer">
        <div className="cd-hd">
          <div>
            <div className="cd-eyebrow">Evidence · {token.token}</div>
            <div className="cd-title">
              <span className="cd-sym">{token.token}</span>
              <span className="cd-pair mono">{token.pair}</span>
            </div>
            <div className="cd-addr mono">{token.tokenSub}</div>
          </div>
          <button className="cd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="cd-stage-banner">
          <span className={"pill pill-" + (labelTone[currentLabelFor(token.bin)] || "muted")}>{currentLabelFor(token.bin)}</span>
          <span className="cd-banner-target">suggested <b className="ember mono">{token.suggested}</b></span>
          <ConfidenceChip value={token.confidence} />
          <ReviewStatusPill value={deriveReviewStatus(token)} />
        </div>

        <div className="research-banner">
          <span className="research-banner-icon">⚠</span>
          <span><b>Research-only labels.</b> These do not affect Phoenix live decisions.</span>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Original Decision Context</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Decision</span><b><Pill tone={decisionTone[token.decision] || "muted"} dim>{token.decision}</Pill></b></div>
            <div className="cd-kv"><span>Reason</span><b className="mono ember">{token.reason}</b></div>
            <div className="cd-kv"><span>Filters</span><b><Pill tone={token.filtersTone} dim>{token.filters}</Pill></b></div>
            <div className="cd-kv"><span>Pair quote</span><b>{token.pairQuote}</b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Outcome Context</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Outcome</span><b><OutcomePill value={token.outcome} /></b></div>
            <div className="cd-kv"><span>Max bounce</span><b className={token.maxBounce > 0 ? "ok mono" : "warn mono"}>{token.maxBounce != null ? (token.maxBounce > 0 ? "+" : "") + token.maxBounce + "%" : "—"}</b></div>
            <div className="cd-kv"><span>Max drawdown</span><b className="warn mono">{token.maxDrawdown != null ? token.maxDrawdown + "%" : "—"}</b></div>
            <div className="cd-kv"><span>ATH reclaim</span><b>{token.athReclaim === true ? "Yes ★" : token.athReclaim === false ? "No" : "—"}</b></div>
            <div className="cd-kv"><span>Data quality</span><b><QualityChip value={token.dataQuality} /></b></div>
            <div className="cd-kv"><span>Age in queue</span><b className="mono">{token.age}</b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Evidence</div>
          <p className="cd-note">{token.evidence}</p>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Label Note</div>
          <p className="cd-note cd-note-warn">{token.note}</p>
        </div>

        {conflict && (
          <div className="cd-section">
            <div className="cd-section-hd">Conflict</div>
            <div className="cd-blocker">
              <div className="cd-blocker-icon">!</div>
              <div className="cd-blocker-body">
                <div className="cd-blocker-title">{conflict.replace(/_/g, " ")}</div>
                <div className="cd-blocker-next">
                  <span className="cd-blocker-next-arrow">→</span>
                  <span>{conflictReason(conflict)}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        <div className="cd-section">
          <div className="cd-section-hd">Move to Bin</div>
          <div className="move-grid">
            {CALIB_BINS.filter((b) => !b.pool).map((b) => (
              <button
                key={b.id}
                className={"move-btn move-btn-" + b.tone + (token.bin === b.id ? " move-btn-active" : "")}
                onClick={() => onMove(token.id, b.id)}
              >
                <span className="move-btn-icon">{b.icon}</span>
                <span>{b.label}</span>
              </button>
            ))}
            <button
              className={"move-btn move-btn-info" + (token.bin === "UNLABELED" ? " move-btn-active" : "")}
              onClick={() => onMove(token.id, "UNLABELED")}
            >
              <span className="move-btn-icon">↺</span>
              <span>Back to Unlabeled</span>
            </button>
          </div>
        </div>

        <div className="cd-foot">
          <span className="foot-mute">research-only · labels do not affect live decisions</span>
        </div>
      </aside>
    </>
  );
}

function conflictReason(c) {
  return {
    SKIP_RAN: "Phoenix skipped but token ran post-decision.",
    ALERT_DIED: "Phoenix would-alert but token died.",
    LABEL_MISMATCH: "Existing manual label disagrees with new evidence.",
    DATA_CENSORED: "Data quality makes the label unreliable.",
    USDC_UNCALIBRATED: "USDC pair — no separate calibration exists yet.",
    OUTCOME_CONFLICT: "Outcome contradicts the original decision logic.",
    FILTER_FALSE_POSITIVE: "Filter flagged a clean token — missed organic case.",
    FILTER_FALSE_NEGATIVE: "Filter passed a token that died — missed bundle/rug.",
  }[c] || "Conflict between evidence and existing state.";
}

// ─── Page ────────────────────────────────────────────────────────────
function CalibrationPage() {
  const [tokens, setTokens] = React.useState(CalibInitialTokens);
  const [selected, setSelected] = React.useState(null);
  const [draggingId, setDraggingId] = React.useState(null);
  const [dropTarget, setDropTarget] = React.useState(null);
  const [labelFilter, setLabelFilter] = React.useState("ALL");
  const [confFilter, setConfFilter] = React.useState("ALL");
  const [pairFilter, setPairFilter] = React.useState("ALL");
  const [outcomeFilter, setOutcomeFilter] = React.useState("ALL");
  const [qualityFilter, setQualityFilter] = React.useState("ALL");
  const [reviewFilter, setReviewFilter] = React.useState("ALL");

  // Sync the selected token when state changes
  React.useEffect(() => {
    if (selected) {
      const fresh = tokens.find((t) => t.id === selected.id);
      if (fresh && fresh !== selected) setSelected(fresh);
    }
  }, [tokens]);

  const moveToken = (id, binId) => {
    setTokens((curr) => curr.map((t) => t.id === id ? { ...t, bin: binId } : t));
  };

  const byBin = (binId) => tokens.filter((t) => t.bin === binId);

  // Summary — 11 tiles
  const Summary = [
    { label: "Unlabeled",        value: byBin("UNLABELED").length, tone: "info" },
    { label: "Organic",          value: byBin("ORGANIC").length,   tone: "ok" },
    { label: "Bundled",          value: byBin("BUNDLED").length,   tone: "ember" },
    { label: "Washy",            value: byBin("WASHY").length,     tone: "warn" },
    { label: "Scam / Rug",       value: byBin("RUG").length,       tone: "bad" },
    { label: "Low Quality",      value: byBin("LOW_QUALITY").length, tone: "bad" },
    { label: "Ambiguous",        value: byBin("AMBIGUOUS").length, tone: "muted" },
    { label: "Needs Review",     value: byBin("NEEDS_REVIEW").length + tokens.filter((t) => t.bin === "UNLABELED" && detectConflict(t)).length, tone: "ember" },
    { label: "Excluded",         value: byBin("EXCLUDE").length + tokens.filter((t) => deriveReviewStatus(t) === "EXCLUDED" && t.bin !== "EXCLUDE").length, tone: "muted" },
    { label: "Gold Set",         value: byBin("GOLD").length,      tone: "called" },
    { label: "Label Conflicts",  value: tokens.filter((t) => detectConflict(t)).length, tone: "bad" },
  ];

  // Filtering for queue table
  let queueRows = [...tokens];
  if (labelFilter === "UNLABELED") queueRows = queueRows.filter((t) => t.bin === "UNLABELED");
  else if (labelFilter === "NEEDS_REVIEW") queueRows = queueRows.filter((t) => t.bin === "NEEDS_REVIEW" || (t.bin === "UNLABELED" && detectConflict(t)));
  else if (labelFilter === "CONFLICTS") queueRows = queueRows.filter((t) => detectConflict(t));
  else if (labelFilter === "ORGANIC") queueRows = queueRows.filter((t) => t.bin === "ORGANIC" || t.bin === "GOLD");
  else if (labelFilter === "BUNDLED") queueRows = queueRows.filter((t) => t.bin === "BUNDLED");
  else if (labelFilter === "WASHY") queueRows = queueRows.filter((t) => t.bin === "WASHY");
  else if (labelFilter === "RUG") queueRows = queueRows.filter((t) => t.bin === "RUG");
  else if (labelFilter === "LOW_QUALITY") queueRows = queueRows.filter((t) => t.bin === "LOW_QUALITY");
  else if (labelFilter === "EXCLUDED") queueRows = queueRows.filter((t) => t.bin === "EXCLUDE");
  else if (labelFilter === "GOLD") queueRows = queueRows.filter((t) => t.bin === "GOLD");
  if (confFilter !== "ALL") queueRows = queueRows.filter((t) => t.confidence === confFilter);
  if (pairFilter !== "ALL") queueRows = queueRows.filter((t) => t.pairQuote === pairFilter);
  if (outcomeFilter !== "ALL") queueRows = queueRows.filter((t) => t.outcome === outcomeFilter);
  if (qualityFilter !== "ALL") queueRows = queueRows.filter((t) => t.dataQuality === qualityFilter);
  if (reviewFilter !== "ALL") queueRows = queueRows.filter((t) => deriveReviewStatus(t) === reviewFilter);

  // Conflicts panel rows
  const conflicts = tokens.map((t) => ({ ...t, _c: detectConflict(t) })).filter((t) => t._c);

  // Gold groups
  const goldGroups = (() => {
    const g = {
      "Gold Organic": [], "Gold Bundle / Rug": [], "Gold Washy": [], "Gold Dead": [], "Gold Exclusion": [],
    };
    tokens.filter((t) => t.bin === "GOLD").forEach((t) => {
      const s = t.suggested;
      if (s === "SUGGEST_ORGANIC") g["Gold Organic"].push(t);
      else if (s === "SUGGEST_BUNDLED") g["Gold Bundle / Rug"].push(t);
      else if (s === "SUGGEST_RUG") g["Gold Bundle / Rug"].push(t);
      else if (s === "SUGGEST_WASHY") g["Gold Washy"].push(t);
      else if (s === "SUGGEST_EXCLUDE") g["Gold Exclusion"].push(t);
      else g["Gold Organic"].push(t);
    });
    return g;
  })();

  const handleDragStart = (id) => (e) => {
    setDraggingId(id);
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", id); } catch {}
  };
  const handleDragEnd = () => { setDraggingId(null); setDropTarget(null); };
  const handleDragOver = (binId) => (e) => { e.preventDefault(); setDropTarget(binId); e.dataTransfer.dropEffect = "move"; };
  const handleDragLeave = (binId) => () => { if (dropTarget === binId) setDropTarget(null); };
  const handleDrop = (binId) => (e) => {
    e.preventDefault();
    if (draggingId) moveToken(draggingId, binId);
    setDraggingId(null);
    setDropTarget(null);
  };

  return (
    <div className="live-page">
      <DemoDataBanner>
        Calibration is local-only for now — bin labels live in this browser session only and are never written back. Tokens shown are the design demo dataset (not PHX2 data).
      </DemoDataBanner>
      {/* Header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Research Workbench</div>
          <h1 className="live-h1">
            Calibration
            <span className="live-pulse"><PulseDot /> {byBin("UNLABELED").length} unlabeled</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <span className="meta-chunk"><span className="meta-k">gold</span><span className="meta-v">{byBin("GOLD").length}</span></span>
          <span className="meta-chunk"><span className="meta-k">conflicts</span><span className="meta-v" style={{ color: "#ff8a7a" }}>{conflicts.length}</span></span>
        </div>
      </div>

      {/* Research-only banner */}
      <div className="research-banner research-banner-large">
        <span className="research-banner-icon">⚠</span>
        <div>
          <div className="research-banner-title">Research-only labels</div>
          <div className="research-banner-sub">These do not affect Phoenix live decisions, pings, filters, policies, or outcomes.</div>
        </div>
      </div>

      {/* Summary strip */}
      <div className="cand-summary out-summary">
        {Summary.map((s, i) => (
          <div key={i} className={"cand-tile cand-tile-" + (s.tone || "info")}>
            <div className="cand-tile-val">{s.value}</div>
            <div className="cand-tile-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Bins Board */}
      <Card
        eyebrow="01 · Workbench"
        title="Label Bins"
        right={<span className="meta-chunk"><span className="meta-k">drag</span><span className="meta-v">tokens between bins</span></span>}
      >
        <div className="bins-board">
          {CALIB_BINS.map((b) => {
            const items = byBin(b.id);
            const isTarget = dropTarget === b.id;
            return (
              <div
                key={b.id}
                className={"bin bin-" + b.tone + (isTarget ? " bin-target" : "") + (b.pool ? " bin-pool" : "")}
                onDragOver={handleDragOver(b.id)}
                onDragLeave={handleDragLeave(b.id)}
                onDrop={handleDrop(b.id)}
              >
                <div className="bin-hd">
                  <div className="bin-name">
                    {b.icon && <span className="bin-icon">{b.icon}</span>}
                    <span>{b.label}</span>
                  </div>
                  <span className="bin-count mono">{items.length}</span>
                </div>
                <div className="bin-body">
                  {items.length === 0 && (
                    <div className="bin-empty">drop here</div>
                  )}
                  {items.map((t) => (
                    <TokenChip
                      key={t.id}
                      t={t}
                      onClick={() => setSelected(t)}
                      draggable
                      onDragStart={handleDragStart(t.id)}
                      onDragEnd={handleDragEnd}
                      isDragging={draggingId === t.id}
                    />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Filters + Queue table */}
      <div className="dec-filter-row">
        <div className="dec-filter-group">
          <span className="dec-filter-label">View</span>
          {["ALL","UNLABELED","NEEDS_REVIEW","CONFLICTS","ORGANIC","BUNDLED","WASHY","RUG","LOW_QUALITY","EXCLUDED","GOLD"].map((f) => (
            <span key={f} className={"filter-chip " + (labelFilter === f ? "active" : "")} onClick={() => setLabelFilter(f)}>
              {f === "ALL" ? "All" : f.replace(/_/g, " ").toLowerCase().replace(/^\w/, c => c.toUpperCase())}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Confidence</span>
          {["ALL","HIGH","MEDIUM","LOW"].map((f) => (
            <span key={f} className={"filter-chip " + (confFilter === f ? "active" : "")} onClick={() => setConfFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Pair</span>
          {["ALL","SOL","USDC","UNKNOWN"].map((f) => (
            <span key={f} className={"filter-chip " + (pairFilter === f ? "active" : "")} onClick={() => setPairFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Outcome</span>
          {["ALL","HIT","MISS","SAVED_BY_SKIP","MISSED_RUNNER","CENSORED","PARTIAL","DEAD"].map((f) => (
            <span key={f} className={"filter-chip " + (outcomeFilter === f ? "active" : "")} onClick={() => setOutcomeFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Data</span>
          {["ALL","COMPLETE","PARTIAL","MISSING_ATH","STALE"].map((f) => (
            <span key={f} className={"filter-chip " + (qualityFilter === f ? "active" : "")} onClick={() => setQualityFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Review</span>
          {["ALL","UNREVIEWED","REVIEWED","CONFLICT","NEEDS_MORE_DATA","GOLD_CANDIDATE","EXCLUDED"].map((f) => (
            <span key={f} className={"filter-chip " + (reviewFilter === f ? "active" : "")} onClick={() => setReviewFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
      </div>

      <Card
        eyebrow="02 · Queue"
        title="Token Labeling Queue"
        right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{queueRows.length}</span></span>}
      >
        <div className="tbl-wrap">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Token</th>
                <th>Pair</th>
                <th>Decision</th>
                <th>Reason</th>
                <th>Outcome</th>
                <th>Current Label</th>
                <th>Suggested</th>
                <th>Confidence</th>
                <th>Evidence</th>
                <th>Data</th>
                <th>Review Status</th>
                <th>Age</th>
              </tr>
            </thead>
            <tbody>
              {queueRows.map((t) => {
                const conflict = detectConflict(t);
                return (
                  <tr key={t.id} onClick={() => setSelected(t)} className={selected && selected.id === t.id ? "row-active" : ""}>
                    <td>
                      <div className="tok">
                        <span className="tok-sym">{t.token}</span>
                        <span className="tok-sub">{t.tokenSub}</span>
                      </div>
                    </td>
                    <td className="mono">{t.pair}</td>
                    <td><Pill tone={decisionTone[t.decision] || "muted"} dim>{t.decision}</Pill></td>
                    <td><span className="reason-chip mono">{t.reason}</span></td>
                    <td><OutcomePill value={t.outcome} /></td>
                    <td><span className={"pill pill-" + (labelTone[currentLabelFor(t.bin)] || "muted") + " pill-dim"}>{currentLabelFor(t.bin)}</span></td>
                    <td><span className="suggest-chip mono">{t.suggested}</span></td>
                    <td><ConfidenceChip value={t.confidence} /></td>
                    <td className="reason ev-cell">{t.evidence}</td>
                    <td><QualityChip value={t.dataQuality} /></td>
                    <td><ReviewStatusPill value={deriveReviewStatus(t)} /></td>
                    <td className="mono mute">{t.age}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Conflicts + Gold */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="03 · Conflicts"
          title="Label Conflicts"
          right={<span className="meta-chunk"><span className="meta-k">total</span><span className="meta-v">{conflicts.length}</span></span>}
        >
          {conflicts.length === 0 ? (
            <div className="empty-state">No conflicts detected.</div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl tbl-clickable">
                <thead>
                  <tr>
                    <th>Token</th>
                    <th>Current</th>
                    <th>Suggested</th>
                    <th>Conflict</th>
                    <th>Evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {conflicts.map((t) => (
                    <tr key={t.id} onClick={() => setSelected(t)}>
                      <td><span className="tok-sym">{t.token}</span> <span className="mono mute">/ {t.pairQuote}</span></td>
                      <td><span className={"pill pill-" + (labelTone[currentLabelFor(t.bin)] || "muted") + " pill-dim"}>{currentLabelFor(t.bin)}</span></td>
                      <td><span className="suggest-chip mono">{t.suggested}</span></td>
                      <td><span className="pill pill-bad pill-dim">{t._c}</span></td>
                      <td className="reason ev-cell">{conflictReason(t._c)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          eyebrow="04 · Gold Set"
          title="High-Confidence Reference Examples"
          right={<span className="meta-chunk"><span className="meta-k">gold</span><span className="meta-v">{byBin("GOLD").length}</span></span>}
        >
          <div className="gold-groups">
            {Object.entries(goldGroups).map(([name, rows]) => (
              <div key={name} className="gold-group">
                <div className="gold-group-hd">
                  <span className="gold-group-name">★ {name}</span>
                  <span className="gold-group-count">{rows.length}</span>
                </div>
                <div className="gold-rows">
                  {rows.length === 0 ? (
                    <div className="bin-empty" style={{ padding: "8px 4px" }}>—</div>
                  ) : rows.map((t) => (
                    <div key={t.id} className="gold-row" onClick={() => setSelected(t)}>
                      <span><span className="tok-sym">{t.token}</span> <span className="mono mute">/ {t.pairQuote}</span></span>
                      <span className="mono mute" style={{ fontSize: 11 }}>{t.reason}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="dq-note">
            Gold Set examples are <b>high-confidence</b>, <b>clean-data</b> reference tokens for future calibration. Drag any token into the <b>Gold Standard</b> bin to add it.
          </div>
        </Card>
      </div>

      <div className="live-foot">
        <span className="foot-mute">Front-end mock · research-only · click any token for evidence and labeling</span>
        <span className="foot-mute foot-pulse"><PulseDot /> labeling workbench</span>
      </div>

      <EvidenceDrawer token={selected} onClose={() => setSelected(null)} onMove={moveToken} />
    </div>
  );
}

window.CalibrationPage = CalibrationPage;
Object.assign(window, { ConfidenceChip });
