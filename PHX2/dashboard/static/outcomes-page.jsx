// Phoenix — Outcomes page (proof layer)
// Design-mock kept as fallback; real data (paper closed positions / realized
// outcomes) from usePhxData("outcomes", …).

const MOCK_OUTCOMES = {
  outcomes: [
    {
      id: "OUT-9821", token: "POPCAT", tokenSub: "9xK3…vB2p", pair: "POPCAT / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T1_DRAWDOWN_CONFIRMED", tier: "T1",
      decisionT: "2h 14m", tAbs: "12:08:51",
      window: "4h", status: "HIT",
      maxBounce: 82.4, maxDrawdown: -8.2, athReclaim: false, timeToResult: "42m",
      filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
      note: "Bounced cleanly off T1 drawdown to +82%.",
    },
    {
      id: "OUT-9820", token: "PNUT", tokenSub: "3xVm…K7Lq", pair: "PNUT / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED", tier: "T2",
      decisionT: "4h 02m", tAbs: "10:20:48",
      window: "6h", status: "HIT",
      maxBounce: 56.1, maxDrawdown: -4.4, athReclaim: false, timeToResult: "2h 14m",
      filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
      note: "Hit T2 target. Bounced +56% in 2h 14m.",
    },
    {
      id: "OUT-9819", token: "PEPE", tokenSub: "5n4Q…aR2v", pair: "PEPE / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T1_DRAWDOWN_CONFIRMED", tier: "T1",
      decisionT: "6h 22m", tAbs: "08:00:24",
      window: "24h", status: "RECLAIMED_ATH",
      maxBounce: 124.0, maxDrawdown: -2.1, athReclaim: true, timeToResult: "6h 22m",
      filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
      note: "Reclaimed prior ATH 6h after Phoenix decision. +124% peak.",
    },
    {
      id: "OUT-9818", token: "GOAT", tokenSub: "X2pQ…4nMv", pair: "GOAT / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED", tier: "T2",
      decisionT: "8h 12m", tAbs: "06:09:54",
      window: "12h", status: "MISS",
      maxBounce: 12.4, maxDrawdown: -68.0, athReclaim: false, timeToResult: "4h 18m",
      filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
      note: "Small bounce (+12%) then deeper drawdown to -68%. Missed.",
    },
    {
      id: "OUT-9817", token: "CHILL", tokenSub: "7Hp1…D9Mz", pair: "CHILL / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED", tier: "T2",
      decisionT: "14m", tAbs: "14:08:14",
      window: "4h", status: "PENDING",
      maxBounce: 4.2, maxDrawdown: -1.1, athReclaim: null, timeToResult: "—",
      filters: "ALL_PASS", filtersTone: "ok", dataQuality: "COMPLETE",
      note: "Outcome window still open (3h 46m remaining).",
    },
    {
      id: "OUT-9816", token: "WIF", tokenSub: "EKp…1F2h", pair: "WIF / USDC", pairQuote: "USDC",
      decision: "OBSERVE_ONLY", reason: "USDC_PAIR_OBSERVE_ONLY", tier: "T2",
      decisionT: "1h 50m", tAbs: "12:32:30",
      window: "4h", status: "PARTIAL",
      maxBounce: 31.2, maxDrawdown: -6.4, athReclaim: false, timeToResult: "1h 50m",
      filters: "USDC_PAIR", filtersTone: "watching", dataQuality: "COMPLETE",
      note: "USDC lane uncalibrated — bounce observed but not directly comparable.",
    },
    {
      id: "OUT-9815", token: "BRETT", tokenSub: "9pBn…2KqL", pair: "BRETT / SOL", pairQuote: "SOL",
      decision: "OBSERVE_ONLY", reason: "POLICY_PENDING_REVIEW", tier: "T2",
      decisionT: "51m", tAbs: "13:31:18",
      window: "4h", status: "LATER_CANDIDATE",
      maxBounce: 18.0, maxDrawdown: -3.1, athReclaim: false, timeToResult: "1h 22m",
      filters: "POLICY_REVIEW", filtersTone: "watching", dataQuality: "COMPLETE",
      note: "Re-entered candidate queue after policy review window opened.",
    },
    {
      id: "OUT-9814", token: "CHEEMS", tokenSub: "Cq8N…vK3R", pair: "CHEEMS / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "BUNDLE_RISK", tier: "T1",
      decisionT: "5m", tAbs: "14:17:42",
      window: "1h", status: "SAVED_BY_SKIP",
      maxBounce: -8.0, maxDrawdown: -71.0, athReclaim: false, timeToResult: "38m",
      filters: "BUNDLE_RISK", filtersTone: "bad", dataQuality: "COMPLETE",
      note: "Token dropped another -71% after Phoenix skipped. Filter justified.",
    },
    {
      id: "OUT-9813", token: "MOODENG", tokenSub: "9vRk…X2pN", pair: "MOODENG / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "LOW_LIQUIDITY", tier: "T2",
      decisionT: "18s", tAbs: "14:22:36",
      window: "1h", status: "SAVED_BY_SKIP",
      maxBounce: -3.2, maxDrawdown: -64.0, athReclaim: false, timeToResult: "12m",
      filters: "LIQ_DROP", filtersTone: "bad", dataQuality: "COMPLETE",
      note: "Liquidity continued to collapse. Skip saved capital.",
    },
    {
      id: "OUT-9812", token: "NEIRO", tokenSub: "Vm8K…3pXr", pair: "NEIRO / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "LOW_LIQUIDITY", tier: "T3",
      decisionT: "38m", tAbs: "13:44:48",
      window: "1h", status: "SAVED_BY_SKIP",
      maxBounce: -5.1, maxDrawdown: -82.0, athReclaim: false, timeToResult: "22m",
      filters: "LOW_LIQ", filtersTone: "bad", dataQuality: "PARTIAL",
      note: "Liquidity stayed thin. Token decayed further.",
    },
    {
      id: "OUT-9811", token: "GIGA", tokenSub: "Lq2N…8rXm", pair: "GIGA / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "LOW_LIQUIDITY", tier: "T2",
      decisionT: "42m", tAbs: "13:40:23",
      window: "4h", status: "MISSED_RUNNER",
      maxBounce: 94.0, maxDrawdown: -8.0, athReclaim: false, timeToResult: "2h 06m",
      filters: "LOW_LIQ", filtersTone: "bad", dataQuality: "COMPLETE",
      note: "Liquidity recovered post-decision. Token ran +94%. Possible miss.",
    },
    {
      id: "OUT-9810", token: "BRETT2", tokenSub: "Kn4P…7QmZ", pair: "BRETT2 / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "BELOW_TIER_THRESHOLD", tier: "--",
      decisionT: "1h 14m", tAbs: "13:08:42",
      window: "6h", status: "MISSED_RUNNER",
      maxBounce: 147.0, maxDrawdown: -12.0, athReclaim: false, timeToResult: "3h 22m",
      filters: "EVAL", filtersTone: "info", dataQuality: "COMPLETE",
      note: "Drawdown deepened to -64% then bounced +147%. Phoenix missed the runner.",
    },
    {
      id: "OUT-9809", token: "BONK", tokenSub: "DezX…8mNq", pair: "BONK / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "ATH_UNKNOWN", tier: "--",
      decisionT: "1m", tAbs: "14:21:54",
      window: "4h", status: "CENSORED",
      maxBounce: null, maxDrawdown: null, athReclaim: null, timeToResult: "—",
      filters: "ATH_UNKNOWN", filtersTone: "warn", dataQuality: "MISSING_ATH",
      note: "ATH never confirmed. Outcome cannot be measured.",
    },
    {
      id: "OUT-9808", token: "CASH", tokenSub: "8vRm…2WkN", pair: "CASH / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "ATH_UNKNOWN", tier: "--",
      decisionT: "3h 02m", tAbs: "11:20:18",
      window: "12h", status: "CENSORED",
      maxBounce: null, maxDrawdown: null, athReclaim: null, timeToResult: "—",
      filters: "ATH_UNKNOWN", filtersTone: "warn", dataQuality: "MISSING_ATH",
      note: "ATH never confirmed. Outcome cannot be measured.",
    },
    {
      id: "OUT-9807", token: "MOG", tokenSub: "Bx5p…RkLm", pair: "MOG / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "PRICE_STALE", tier: "--",
      decisionT: "2m", tAbs: "14:20:50",
      window: "4h", status: "NO_DATA",
      maxBounce: null, maxDrawdown: null, athReclaim: null, timeToResult: "—",
      filters: "PRICE_STALE", filtersTone: "warn", dataQuality: "STALE",
      note: "Price feed remained stale through the outcome window. No reliable post-decision price.",
    },
    {
      id: "OUT-9806", token: "BORK", tokenSub: "3kQv…6JrN", pair: "BORK / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "FILTER_INCOMPLETE", tier: "--",
      decisionT: "1h", tAbs: "13:21:32",
      window: "4h", status: "CENSORED",
      maxBounce: null, maxDrawdown: null, athReclaim: null, timeToResult: "—",
      filters: "FILTERS_INCOMPLETE", filtersTone: "warn", dataQuality: "FILTER_INCOMPLETE",
      note: "Filter set never completed. Outcome cannot be measured.",
    },
    {
      id: "OUT-9805", token: "DEGEN", tokenSub: "2sNv…UqWk", pair: "DEGEN / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "DEAD_CHART_PATTERN", tier: "--",
      decisionT: "12m", tAbs: "14:10:21",
      window: "4h", status: "DEAD",
      maxBounce: -12.0, maxDrawdown: -97.6, athReclaim: false, timeToResult: "18m",
      filters: "RUG_PATTERN", filtersTone: "bad", dataQuality: "COMPLETE",
      note: "Token died as predicted. -97% confirmed.",
    },
    {
      id: "OUT-9804", token: "BOME", tokenSub: "4nL2…XmQr", pair: "BOME / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "DEAD_CHART_PATTERN", tier: "--",
      decisionT: "21m", tAbs: "14:01:09",
      window: "6h", status: "DEAD",
      maxBounce: -8.4, maxDrawdown: -95.0, athReclaim: false, timeToResult: "32m",
      filters: "RUG_PATTERN", filtersTone: "bad", dataQuality: "COMPLETE",
      note: "Confirmed rug pattern. Token decayed -95%.",
    },
    {
      id: "OUT-9803", token: "FRESH", tokenSub: "8mP2…W3Lk", pair: "FRESH / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "MIGRATION_TOO_FRESH", tier: "--",
      decisionT: "18m", tAbs: "14:04:11",
      window: "4h", status: "LATER_CANDIDATE",
      maxBounce: 14.0, maxDrawdown: -22.0, athReclaim: false, timeToResult: "1h 02m",
      filters: "MIGRATION_AGE", filtersTone: "warn", dataQuality: "PARTIAL",
      note: "Token re-entered candidate queue after migration age threshold crossed.",
    },
    {
      id: "OUT-9802", token: "ANDY", tokenSub: "Hk4Q…2vRt", pair: "ANDY / SOL", pairQuote: "SOL",
      decision: "WATCH", reason: "BELOW_TIER_THRESHOLD", tier: "--",
      decisionT: "31m", tAbs: "13:51:50",
      window: "4h", status: "LATER_ALERTED",
      maxBounce: 8.0, maxDrawdown: -52.0, athReclaim: false, timeToResult: "1h 44m",
      filters: "EVAL", filtersTone: "info", dataQuality: "COMPLETE",
      note: "Drawdown crossed T3 1h 44m after WATCH. Promoted to WOULD_ALERT.",
    },
    {
      id: "OUT-9801", token: "MEW", tokenSub: "7vXk…N3qR", pair: "MEW / SOL", pairQuote: "SOL",
      decision: "WATCH", reason: "WAITING_FOR_PULLBACK", tier: "--",
      decisionT: "1h 22m", tAbs: "13:00:11",
      window: "6h", status: "EXPIRED",
      maxBounce: 3.4, maxDrawdown: -8.0, athReclaim: false, timeToResult: "—",
      filters: "EVAL", filtersTone: "info", dataQuality: "COMPLETE",
      note: "Outcome window expired with no meaningful pullback. Token still trending.",
    },
    {
      id: "OUT-9800", token: "TURBO", tokenSub: "7q1v…J3xZ", pair: "TURBO / SOL", pairQuote: "SOL",
      decision: "WATCH", reason: "BELOW_TIER_THRESHOLD", tier: "--",
      decisionT: "41s", tAbs: "14:22:13",
      window: "4h", status: "DIED",
      maxBounce: -4.0, maxDrawdown: -78.0, athReclaim: false, timeToResult: "2h 14m",
      filters: "EVAL", filtersTone: "info", dataQuality: "COMPLETE",
      note: "Token decayed before reaching tier. Dropped from WATCH.",
    },
  ],
};

// ─── Tones ───────────────────────────────────────────────────────────
const outcomeTone = {
  HIT: "ok",
  RECLAIMED_ATH: "ok",
  SAVED_BY_SKIP: "ok",
  LATER_ALERTED: "ember",
  PENDING: "ember",
  PARTIAL: "watching",
  LATER_CANDIDATE: "watching",
  MISS: "bad",
  MISSED_RUNNER: "bad",
  DEAD: "bad",
  DIED: "bad",
  CENSORED: "muted",
  NO_DATA: "muted",
  EXPIRED: "muted",
};
function OutcomePill({ value }) {
  return <span className={"pill pill-" + (outcomeTone[value] || "muted")}>{value}</span>;
}

const outcomeIcon = {
  HIT: "✓", RECLAIMED_ATH: "✓★", SAVED_BY_SKIP: "✓",
  LATER_ALERTED: "↑", PENDING: "◐",
  PARTIAL: "≈", LATER_CANDIDATE: "→",
  MISS: "✕", MISSED_RUNNER: "↗✕", DEAD: "☠", DIED: "☠",
  CENSORED: "∅", NO_DATA: "∅", EXPIRED: "⏳",
};

// ─── Summary ─────────────────────────────────────────────────────────
const byStatusOf = (list, s) => list.filter((o) => o.status === s).length;
function buildOutcomeSummary(list) {
  const byStatus = (s) => byStatusOf(list, s);
  return [
    { label: "Total Tracked", value: list.length, tone: "info" },
    { label: "Hits", value: byStatus("HIT") + byStatus("RECLAIMED_ATH"), tone: "ok" },
    { label: "Misses", value: byStatus("MISS") + byStatus("MISSED_RUNNER"), tone: "bad" },
    { label: "Pending", value: byStatus("PENDING"), tone: "called" },
    { label: "Censored", value: byStatus("CENSORED"), tone: "muted" },
    { label: "Partial", value: byStatus("PARTIAL"), tone: "watching" },
    { label: "ATH Reclaims", value: list.filter((o) => o.athReclaim === true).length, tone: "ember" },
    { label: "Dead / Rug", value: byStatus("DEAD") + byStatus("DIED"), tone: "bad" },
    { label: "Skips That Saved", value: byStatus("SAVED_BY_SKIP"), tone: "ok" },
    { label: "Skips That Ran", value: byStatus("MISSED_RUNNER"), tone: "bad" },
  ];
}

// ─── Performance by Decision Type (grouped buckets per spec) ─────────
function perfByDecision(list) {
  const out = {
    WOULD_ALERT: { Hit: 0, Miss: 0, Pending: 0, Censored: 0 },
    SKIP:        { "Saved by Skip": 0, "Missed Runner": 0, Censored: 0, "No Data": 0 },
    OBSERVE_ONLY:{ Partial: 0, Pending: 0, Uncalibrated: 0, "Later Candidate": 0 },
    WATCH:       { "Later Alerted": 0, Expired: 0, Died: 0 },
    PAPER_TRADE: { Hit: 0, Miss: 0, Pending: 0, Partial: 0 },
  };
  list.forEach((o) => {
    if (o.decision === "PAPER_TRADE") {
      if (o.status === "HIT") out.PAPER_TRADE.Hit++;
      else if (o.status === "MISS") out.PAPER_TRADE.Miss++;
      else if (o.status === "PENDING") out.PAPER_TRADE.Pending++;
      else if (o.status === "PARTIAL") out.PAPER_TRADE.Partial++;
      return;
    }
    if (o.decision === "WOULD_ALERT") {
      if (o.status === "HIT" || o.status === "RECLAIMED_ATH") out.WOULD_ALERT.Hit++;
      else if (o.status === "MISS") out.WOULD_ALERT.Miss++;
      else if (o.status === "PENDING") out.WOULD_ALERT.Pending++;
      else if (o.status === "CENSORED") out.WOULD_ALERT.Censored++;
    } else if (o.decision === "SKIP") {
      if (o.status === "SAVED_BY_SKIP" || o.status === "DEAD") out.SKIP["Saved by Skip"]++;
      else if (o.status === "MISSED_RUNNER") out.SKIP["Missed Runner"]++;
      else if (o.status === "CENSORED") out.SKIP.Censored++;
      else if (o.status === "NO_DATA") out.SKIP["No Data"]++;
    } else if (o.decision === "OBSERVE_ONLY") {
      if (o.status === "PARTIAL") out.OBSERVE_ONLY.Partial++;
      else if (o.status === "PENDING") out.OBSERVE_ONLY.Pending++;
      else if (o.status === "LATER_CANDIDATE") out.OBSERVE_ONLY["Later Candidate"]++;
      if (o.reason === "USDC_PAIR_OBSERVE_ONLY") out.OBSERVE_ONLY.Uncalibrated++;
    } else if (o.decision === "WATCH") {
      if (o.status === "LATER_ALERTED") out.WATCH["Later Alerted"]++;
      else if (o.status === "EXPIRED") out.WATCH.Expired++;
      else if (o.status === "DIED") out.WATCH.Died++;
    }
  });
  return out;
}

// ─── Performance by Reason Code ──────────────────────────────────────
function perfByReason(list) {
  const map = {};
  list.forEach((o) => {
    if (!map[o.reason]) map[o.reason] = {};
    map[o.reason][o.status] = (map[o.reason][o.status] || 0) + 1;
  });
  return map;
}

// ─── Censored / Partial groups ───────────────────────────────────────
function censoredGroups(list) {
  const groups = {
    "ATH unknown": [],
    "Price stale": [],
    "Filter incomplete": [],
    "USDC pair uncalibrated": [],
    "Migration too fresh": [],
  };
  list.forEach((o) => {
    const censoredish = ["CENSORED", "NO_DATA", "PARTIAL", "LATER_CANDIDATE", "EXPIRED"].includes(o.status);
    if (!censoredish) return;
    if (o.reason === "ATH_UNKNOWN") groups["ATH unknown"].push(o);
    else if (o.reason === "PRICE_STALE") groups["Price stale"].push(o);
    else if (o.reason === "FILTER_INCOMPLETE") groups["Filter incomplete"].push(o);
    else if (o.reason === "USDC_PAIR_OBSERVE_ONLY") groups["USDC pair uncalibrated"].push(o);
    else if (o.reason === "MIGRATION_TOO_FRESH") groups["Migration too fresh"].push(o);
  });
  return groups;
}

// ─── Outcome explanation ─────────────────────────────────────────────
function outcomeExplain(o) {
  if (o.explanation) return o.explanation;
  if (o.decision === "PAPER_TRADE") {
    return `Paper-engine outcome for ${o.token}: ${o.status}. ${o.note || ""}`;
  }
  if (o.status === "HIT") return `Phoenix's ${o.decision} on ${o.token} was correct. Drawdown bounced ${o.maxBounce}% within the outcome window — classified HIT.`;
  if (o.status === "RECLAIMED_ATH") return `${o.token} reclaimed its prior ATH after Phoenix's ${o.decision}. Outcome classified RECLAIMED_ATH — strongest possible hit.`;
  if (o.status === "MISS") return `Phoenix alerted ${o.token} but the bounce stalled at ${o.maxBounce}% before reversing to ${o.maxDrawdown}%. Classified MISS.`;
  if (o.status === "PENDING") return `Outcome window for ${o.token} is still open. Phoenix is waiting for the post-decision window to close before classifying.`;
  if (o.status === "SAVED_BY_SKIP") return `Phoenix skipped ${o.token}. Post-decision drawdown reached ${o.maxDrawdown}% — the skip was justified.`;
  if (o.status === "MISSED_RUNNER") return `Phoenix skipped ${o.token} for ${o.reason}, but the token ran ${o.maxBounce}% afterwards. Possible missed opportunity.`;
  if (o.status === "CENSORED") return `Outcome could not be measured for ${o.token} — ${o.reason}. Result is censored and not counted in hit/miss stats.`;
  if (o.status === "NO_DATA") return `No reliable post-decision price data for ${o.token}. Outcome cannot be classified.`;
  if (o.status === "PARTIAL") return `Partial outcome for ${o.token}. Pair is on USDC lane (uncalibrated) — bounce observed but not directly comparable.`;
  if (o.status === "DEAD") return `${o.token} died as Phoenix predicted. Drawdown bottomed at ${o.maxDrawdown}%.`;
  if (o.status === "DIED") return `${o.token} decayed before reaching the tier threshold while under WATCH. Dropped from queue.`;
  if (o.status === "LATER_ALERTED") return `${o.token} was placed under WATCH and later crossed the threshold. Promoted to WOULD_ALERT.`;
  if (o.status === "LATER_CANDIDATE") return `${o.token} re-entered the candidate queue after the original blocker cleared.`;
  if (o.status === "EXPIRED") return `Outcome window for ${o.token} expired with no meaningful movement.`;
  return "Outcome recorded by Phoenix.";
}

// ─── Drawer ──────────────────────────────────────────────────────────
function OutcomeDrawer({ outcome, onClose }) {
  if (!outcome) return null;
  return (
    <>
      <div className="cd-scrim" onClick={onClose} />
      <aside className="cd-drawer">
        <div className="cd-hd">
          <div>
            <div className="cd-eyebrow">Outcome Detail · {outcome.id}</div>
            <div className="cd-title">
              <span className="cd-sym">{outcome.token}</span>
              <span className="cd-pair mono">{outcome.pair}</span>
            </div>
            {outcome.mint
              ? <FullCA value={outcome.mint} />
              : <div className="cd-addr mono">{outcome.tokenSub}</div>}
          </div>
          <button className="cd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="cd-stage-banner">
          <OutcomePill value={outcome.status} />
          <span className="cd-banner-target reason-chip mono">{outcome.reason}</span>
          <span className="cd-banner-update meta-chunk">
            <span className="meta-k">decision</span>
            <span className="meta-v">{outcome.tAbs} · {outcome.decisionT} ago</span>
          </span>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Outcome Context</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Original decision</span><b><Pill tone={decisionTone[outcome.decision] || "muted"}>{outcome.decision}</Pill></b></div>
            <div className="cd-kv"><span>Reason</span><b className="mono ember">{outcome.reason}</b></div>
            <div className="cd-kv"><span>Tier</span><b className="mono">{outcome.tier}</b></div>
            <div className="cd-kv"><span>Pair quote</span><b>{outcome.pairQuote}</b></div>
            <div className="cd-kv"><span>Outcome window</span><b className="mono">{outcome.window}</b></div>
            <div className="cd-kv"><span>Time to result</span><b className="mono ember">{outcome.timeToResult}</b></div>
            <div className="cd-kv"><span>Filters</span><b><Pill tone={outcome.filtersTone} dim>{outcome.filters}</Pill></b></div>
            <div className="cd-kv"><span>Data quality</span><b><QualityChip value={outcome.dataQuality} /></b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Price Path</div>
          <div className="path-grid">
            <div className="path-cell">
              <div className="path-lbl">Max Bounce</div>
              <div className={"path-val " + (outcome.maxBounce > 0 ? "ok" : "warn")}>
                {outcome.maxBounce != null ? (outcome.maxBounce > 0 ? "+" : "") + outcome.maxBounce + "%" : "—"}
              </div>
            </div>
            <div className="path-cell">
              <div className="path-lbl">Max Drawdown</div>
              <div className="path-val warn">
                {outcome.maxDrawdown != null ? outcome.maxDrawdown + "%" : "—"}
              </div>
            </div>
            <div className="path-cell">
              <div className="path-lbl">ATH Reclaim</div>
              <div className={"path-val " + (outcome.athReclaim === true ? "ember" : outcome.athReclaim === false ? "muted" : "muted")}>
                {outcome.athReclaim === true ? "Yes ★" : outcome.athReclaim === false ? "No" : "—"}
              </div>
            </div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Why this classification</div>
          <p className="cd-note">{outcomeExplain(outcome)}</p>
          {outcome.note && <p className="cd-note cd-note-warn" style={{ marginTop: 8 }}>{outcome.note}</p>}
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Cross-references</div>
          <div className="xref">
            <span className="xref-link">→ View original decision in <b>Decisions</b></span>
            <span className="xref-link">→ View candidate timeline in <b>Candidates</b></span>
          </div>
        </div>

        <div className="cd-foot">
          <span className="foot-mute">read-only · outcome is replayable</span>
        </div>
      </aside>
    </>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function OutcomesPage() {
  const OutcomeData = usePhxData("outcomes", MOCK_OUTCOMES);
  const live = usePhxLive();
  const [selected, setSelected] = React.useState(null);
  const [statusFilter, setStatusFilter] = React.useState("ALL");
  const [decisionFilter, setDecisionFilter] = React.useState("ALL");
  const [windowFilter, setWindowFilter] = React.useState("24h");

  let rows = [...OutcomeData.outcomes];
  if (statusFilter !== "ALL") rows = rows.filter((o) => o.status === statusFilter);
  if (decisionFilter !== "ALL") rows = rows.filter((o) => o.decision === decisionFilter);

  const OutcomeSummary = buildOutcomeSummary(OutcomeData.outcomes);
  const perfDec = perfByDecision(OutcomeData.outcomes);
  const perfRsn = perfByReason(OutcomeData.outcomes);
  const cens = censoredGroups(OutcomeData.outcomes);

  return (
    <div className="live-page">
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Proof Layer</div>
          <h1 className="live-h1">
            Outcomes
            <span className="live-pulse"><PulseDot /> {OutcomeData.outcomes.length} tracked</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <Selector label="window" value={windowFilter} options={["1h","6h","24h","7d","30d"]} onChange={setWindowFilter} />
          <span className="meta-chunk"><span className="meta-k">hit rate</span><span className="meta-v ok">{
            (() => {
              const closed = OutcomeData.outcomes.filter((o) => !["PENDING","CENSORED","NO_DATA","EXPIRED"].includes(o.status));
              const wins = closed.filter((o) => ["HIT","RECLAIMED_ATH","SAVED_BY_SKIP"].includes(o.status)).length;
              return closed.length ? Math.round(wins / closed.length * 100) + "%" : "—";
            })()
          }</span></span>
        </div>
      </div>

      {/* Summary strip — 10 tiles */}
      <div className="cand-summary out-summary">
        {OutcomeSummary.map((s, i) => (
          <div key={i} className={"cand-tile cand-tile-" + (s.tone || "info")}>
            <div className="cand-tile-val">{s.value}</div>
            <div className="cand-tile-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filter row */}
      <div className="dec-filter-row">
        <div className="dec-filter-group">
          <span className="dec-filter-label">Decision</span>
          {["ALL","PAPER_TRADE","WOULD_ALERT","SKIP","OBSERVE_ONLY","WATCH"].map((f) => (
            <span key={f} className={"filter-chip " + (decisionFilter === f ? "active" : "")} onClick={() => setDecisionFilter(f)}>
              {f === "ALL" ? "All" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Outcome</span>
          {["ALL","HIT","MISS","SAVED_BY_SKIP","MISSED_RUNNER","PENDING","PARTIAL","CENSORED","NO_DATA","DEAD","LATER_ALERTED"].map((f) => (
            <span key={f} className={"filter-chip " + (statusFilter === f ? "active" : "")} onClick={() => setStatusFilter(f)}>
              {f === "ALL" ? "All" : f}
            </span>
          ))}
        </div>
      </div>

      {/* Outcome Ledger */}
      <Card
        eyebrow="01 · Ledger"
        title="Outcome Ledger"
        right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{rows.length}</span></span>}
      >
        <div className="tbl-wrap">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Token</th>
                <th>Pair</th>
                <th>Decision</th>
                <th>Reason</th>
                <th>Tier</th>
                <th>Decision Time</th>
                <th>Window</th>
                <th>Outcome</th>
                <th className="num">Max Bounce</th>
                <th className="num">Max Drawdown</th>
                <th>ATH Reclaim</th>
                <th>Time to Result</th>
                <th>Filters</th>
                <th>Data</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan="14"><div className="empty-state">No closed paper trades yet — outcomes appear after the first paper close</div></td></tr>
              )}
              {rows.map((o) => (
                <tr key={o.id} onClick={() => setSelected(o)} className={selected && selected.id === o.id ? "row-active" : ""}>
                  <td>
                    <div className="tok">
                      <span className="tok-sym">{o.token}</span>
                      <span className="tok-sub">{o.tokenSub}<CopyCA value={o.mint} /></span>
                    </div>
                  </td>
                  <td className="mono">{o.pair}</td>
                  <td><Pill tone={decisionTone[o.decision] || "muted"} dim>{o.decision}</Pill></td>
                  <td><span className="reason-chip mono">{o.reason}</span></td>
                  <td><span className={"tier tier-" + (o.tier === "--" ? "muted" : o.tier.toLowerCase())}>{o.tier}</span></td>
                  <td className="dec-time">
                    <div className="dec-time-rel mono">{o.decisionT}</div>
                    <div className="dec-time-abs mono mute">{o.tAbs}</div>
                  </td>
                  <td><span className="window-chip mono">{o.window}</span></td>
                  <td>
                    <div className="outcome-cell">
                      <span className="outcome-icon">{outcomeIcon[o.status] || "·"}</span>
                      <OutcomePill value={o.status} />
                    </div>
                  </td>
                  <td className={"num mono " + (o.maxBounce == null ? "draw-muted" : o.maxBounce > 0 ? "ok" : "draw-warn")}>
                    {o.maxBounce != null ? (o.maxBounce > 0 ? "+" : "") + o.maxBounce.toFixed(1) + "%" : "—"}
                  </td>
                  <td className={"num mono " + (o.maxDrawdown == null ? "draw-muted" : o.maxDrawdown < -70 ? "draw-bad" : "draw-warn")}>
                    {o.maxDrawdown != null ? o.maxDrawdown.toFixed(1) + "%" : "—"}
                  </td>
                  <td>
                    {o.athReclaim === true ? <span className="ath-chip ath-ember">★ yes</span>
                     : o.athReclaim === false ? <span className="ath-chip ath-muted">no</span>
                     : <span className="ath-chip ath-muted">—</span>}
                  </td>
                  <td className="mono mute">{o.timeToResult}</td>
                  <td><Pill tone={o.filtersTone} dim>{o.filters}</Pill></td>
                  <td><QualityChip value={o.dataQuality} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Performance row */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="02 · Performance"
          title="Performance by Decision Type"
          right={<span className="meta-chunk"><span className="meta-k">window</span><span className="meta-v">{windowFilter}</span></span>}
        >
          <div className="perf-groups">
            {Object.entries(perfDec).map(([dec, buckets]) => {
              const total = Object.values(buckets).reduce((a,b)=>a+b,0);
              return (
                <div key={dec} className="perf-group">
                  <div className="perf-group-hd">
                    <Pill tone={decisionTone[dec] || "muted"}>{dec}</Pill>
                    <span className="perf-group-total mono">{total}</span>
                  </div>
                  <div className="perf-bars">
                    {Object.entries(buckets).map(([name, n]) => (
                      <div key={name} className="perf-bar-row">
                        <span className="perf-bar-name">{name}</span>
                        <span className="perf-bar-track">
                          <span className={"perf-bar-fill perf-fill-" + slugBucket(name)} style={{ width: total ? Math.max(2, n / total * 100) + "%" : "0%" }} />
                        </span>
                        <span className="perf-bar-count mono">{n}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card
          eyebrow="03 · Reason Codes"
          title="Outcome by Reason Code"
          right={<span className="meta-chunk"><span className="meta-k">codes</span><span className="meta-v">{Object.keys(perfRsn).length}</span></span>}
        >
          <div className="rsn-list">
            {Object.entries(perfRsn).sort((a,b) => Object.values(b[1]).reduce((s,n)=>s+n,0) - Object.values(a[1]).reduce((s,n)=>s+n,0)).map(([reason, statuses]) => {
              const total = Object.values(statuses).reduce((s,n) => s+n, 0);
              return (
                <div key={reason} className="rsn-row">
                  <div className="rsn-row-name mono">{reason}</div>
                  <div className="rsn-stack">
                    {Object.entries(statuses).map(([s, n]) => (
                      <span key={s} className={"rsn-seg rsn-seg-" + (outcomeTone[s] || "muted")} style={{ flex: n }} title={`${s}: ${n}`} />
                    ))}
                  </div>
                  <div className="rsn-summary">
                    {Object.entries(statuses).map(([s, n], i) => (
                      <span key={s} className={"rsn-tag rsn-tag-" + (outcomeTone[s] || "muted")}>
                        {n} {s.toLowerCase().replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Censored / Partial panel */}
      <Card
        eyebrow="04 · Censored / Partial"
        title="Unresolved or Unreliable Outcomes"
        right={<span className="meta-chunk"><span className="meta-k">total</span><span className="meta-v">{Object.values(cens).reduce((s,a)=>s+a.length,0)}</span></span>}
      >
        <div className="cens-grid">
          {Object.values(cens).every((g) => !g.length) && (
            <div className="empty-state">No censored or partial outcomes</div>
          )}
          {Object.entries(cens).map(([name, rows]) => {
            if (!rows.length) return null;
            return (
              <div key={name} className="cens-group">
                <div className="cens-group-hd">
                  <span className="cens-group-name">{name}</span>
                  <span className="cens-group-count">{rows.length}</span>
                </div>
                <div className="cens-rows">
                  {rows.map((o) => (
                    <div key={o.id} className="cens-row" onClick={() => setSelected(o)}>
                      <span className="cens-tok"><span className="tok-sym">{o.token}</span> <span className="mono mute">/ {o.pairQuote}</span><CopyCA value={o.mint} /></span>
                      <OutcomePill value={o.status} />
                      <span className="cens-t mono">{o.decisionT}</span>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
        <div className="dq-note">
          Censored and partial outcomes are <b>not counted</b> in hit/miss totals. Phoenix records them honestly so missing data is visible — not hidden inside aggregate stats.
        </div>
      </Card>

      <div className="live-foot">
        <span className="foot-mute">{live ? "artifact-backed · read-only" : "Front-end mock"} · click any row for proof detail · outcomes are read-only</span>
        <span className="foot-mute foot-pulse"><PulseDot /> proof layer</span>
      </div>

      <OutcomeDrawer outcome={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function slugBucket(s) {
  const k = s.toLowerCase();
  if (k.includes("hit") || k.includes("saved") || k.includes("later alerted") || k.includes("reclaim")) return "ok";
  if (k.includes("miss") || k.includes("missed runner") || k.includes("died") || k.includes("dead")) return "bad";
  if (k.includes("pending") || k.includes("partial") || k.includes("later candidate") || k.includes("uncalibrated")) return "ember";
  if (k.includes("censored") || k.includes("no data") || k.includes("expired")) return "muted";
  return "info";
}

window.OutcomesPage = OutcomesPage;
Object.assign(window, { OutcomePill, outcomeTone, outcomeIcon });
