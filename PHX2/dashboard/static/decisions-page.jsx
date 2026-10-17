// Phoenix — Decisions page (audit / decision ledger)
// Design-mock kept as fallback; real data from usePhxData("decisions", …).

const MOCK_DECISIONS = {
  decisions: [
    {
      id: "PHX-12048",
      t: "3s", tAbs: "14:22:51",
      token: "POPCAT", tokenSub: "9xK3…vB2p", pair: "POPCAT / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T1_DRAWDOWN_CONFIRMED",
      tier: "T1", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -61.8, filters: "ALL_PASS", filtersTone: "ok",
      dataQuality: "COMPLETE",
      candidateStateBefore: "NEAR_T1 · 1.6% away",
      knew: ["ATH confirmed at $52.1M", "Price fresh (0.8s)", "Liquidity $1.20M", "Bundle risk 0.12", "Holder concentration 8%"],
      whatWouldChange: "If price went stale > 10s or bundle risk crossed 0.65, decision would have flipped to SKIP.",
    },
    {
      id: "PHX-12047",
      t: "18s", tAbs: "14:22:36",
      token: "MOODENG", tokenSub: "9vRk…X2pN", pair: "MOODENG / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "BUNDLE_RISK",
      tier: "T2", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -64.2, filters: "BUNDLE_RISK", filtersTone: "bad",
      dataQuality: "COMPLETE",
      candidateStateBefore: "FILTER_BLOCKED",
      knew: ["ATH confirmed", "Bundle risk score 0.84 (threshold 0.65)", "14 bundled wallets detected", "Drawdown threshold met"],
      whatWouldChange: "Decision would flip to WOULD_ALERT if bundle risk dropped below 0.65.",
    },
    {
      id: "PHX-12046",
      t: "24s", tAbs: "14:22:30",
      token: "WIF", tokenSub: "EKp…1F2h", pair: "WIF / USDC", pairQuote: "USDC",
      decision: "OBSERVE_ONLY", reason: "USDC_PAIR_OBSERVE_ONLY",
      tier: "T2", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -66.0, filters: "USDC_PAIR", filtersTone: "watching",
      dataQuality: "COMPLETE",
      candidateStateBefore: "USDC_OBSERVE_ONLY",
      knew: ["Pair quoted in USDC, not SOL", "All other gates clean", "Drawdown threshold met"],
      whatWouldChange: "Phoenix does not promote USDC quotes to alerts. Decision would change only if a SOL-paired venue for this token is discovered.",
    },
    {
      id: "PHX-12045",
      t: "41s", tAbs: "14:22:13",
      token: "TURBO", tokenSub: "7q1v…J3xZ", pair: "TURBO / SOL", pairQuote: "SOL",
      decision: "WATCH", reason: "BELOW_TIER_THRESHOLD",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -44.0, filters: "EVAL", filtersTone: "info",
      dataQuality: "COMPLETE",
      candidateStateBefore: "WATCHING · 16.0% away",
      knew: ["Drawdown -44% is below T3 tier threshold (-60%)", "Migration recent (1h 14m)", "Liquidity adequate"],
      whatWouldChange: "If drawdown deepens beyond -60% and migration matures past 2h, candidate would advance.",
    },
    {
      id: "PHX-12044",
      t: "1m", tAbs: "14:21:54",
      token: "BONK", tokenSub: "DezX…8mNq", pair: "BONK / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "ATH_UNKNOWN",
      tier: "--", athState: "UNKNOWN", priceState: "FRESH",
      drawdown: null, filters: "ATH_UNKNOWN", filtersTone: "warn",
      dataQuality: "MISSING_ATH",
      candidateStateBefore: "WAITING_FOR_ATH",
      knew: ["Birdeye returned null ATH", "Price feed fresh but cannot compute drawdown", "Token migrated 3d ago"],
      whatWouldChange: "Token re-enters evaluation when ATH is confirmed by the price source.",
    },
    {
      id: "PHX-12043",
      t: "2m", tAbs: "14:20:50",
      token: "MOG", tokenSub: "Bx5p…RkLm", pair: "MOG / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "PRICE_STALE",
      tier: "--", athState: "CONFIRMED", priceState: "STALE",
      drawdown: -37.1, filters: "PRICE_STALE", filtersTone: "warn",
      dataQuality: "STALE",
      candidateStateBefore: "WAITING_FOR_PRICE",
      knew: ["Price freshness 14.2s (threshold 10s)", "ATH $1.4M confirmed", "Cannot trust drawdown calculation"],
      whatWouldChange: "Decision will be re-run when next price tick arrives under 10s freshness.",
    },
    {
      id: "PHX-12042",
      t: "4m", tAbs: "14:18:48",
      token: "PNUT", tokenSub: "3xVm…K7Lq", pair: "PNUT / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED",
      tier: "T2", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -52.4, filters: "ALL_PASS", filtersTone: "ok",
      dataQuality: "COMPLETE",
      candidateStateBefore: "NEAR_T2 · 2.4% away",
      knew: ["ATH $41M confirmed", "Drawdown crossed T2 threshold", "Liquidity $2.1M", "All filters clean"],
      whatWouldChange: "Decision would flip to SKIP if bundle risk rose above 0.65 or liquidity dropped under $250K.",
    },
    {
      id: "PHX-12041",
      t: "5m", tAbs: "14:17:42",
      token: "CHEEMS", tokenSub: "Cq8N…vK3R", pair: "CHEEMS / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "BUNDLE_RISK",
      tier: "T1", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -62.5, filters: "BUNDLE_RISK", filtersTone: "bad",
      dataQuality: "COMPLETE",
      candidateStateBefore: "FILTER_BLOCKED",
      knew: ["Bundle risk score 0.84", "Drawdown threshold met (-62.5%)", "ATH $14M confirmed"],
      whatWouldChange: "Bundle risk must drop below 0.65 for decision to flip to WOULD_ALERT.",
    },
    {
      id: "PHX-12040",
      t: "8m", tAbs: "14:14:33",
      token: "USELESS", tokenSub: "Hk9Q…7vRt", pair: "USELESS / USDC", pairQuote: "USDC",
      decision: "OBSERVE_ONLY", reason: "USDC_PAIR_OBSERVE_ONLY",
      tier: "T3", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -58.0, filters: "USDC_PAIR", filtersTone: "watching",
      dataQuality: "COMPLETE",
      candidateStateBefore: "USDC_OBSERVE_ONLY",
      knew: ["USDC quote pair", "Drawdown adequate", "ATH confirmed $4.2M"],
      whatWouldChange: "USDC pair gate is absolute — decision remains observe-only.",
    },
    {
      id: "PHX-12039",
      t: "12m", tAbs: "14:10:21",
      token: "DEGEN", tokenSub: "2sNv…UqWk", pair: "DEGEN / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "DEAD_CHART_PATTERN",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -97.6, filters: "RUG_PATTERN", filtersTone: "bad",
      dataQuality: "COMPLETE",
      candidateStateBefore: "DEAD",
      knew: ["Liquidity collapsed from $480K to $8K in 24h", "Holder count dropped 80%", "Volume flatlined"],
      whatWouldChange: "Dead chart pattern is terminal — candidate is dropped from queue.",
    },
    {
      id: "PHX-12038",
      t: "14m", tAbs: "14:08:14",
      token: "CHILL", tokenSub: "7Hp1…D9Mz", pair: "CHILL / SOL", pairQuote: "SOL",
      decision: "CANDIDATE", reason: "BELOW_TIER_THRESHOLD",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -45.1, filters: "EVAL", filtersTone: "info",
      dataQuality: "COMPLETE",
      candidateStateBefore: "—",
      knew: ["Drawdown approaching T2 (4.9% away)", "All filters clean", "Migration mature"],
      whatWouldChange: "If drawdown crosses T2 threshold, candidate will be re-evaluated for WOULD_ALERT.",
    },
    {
      id: "PHX-12037",
      t: "18m", tAbs: "14:04:11",
      token: "FRESH", tokenSub: "8mP2…W3Lk", pair: "FRESH / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "MIGRATION_TOO_FRESH",
      tier: "--", athState: "NEW", priceState: "FRESH",
      drawdown: -22.0, filters: "MIGRATION_AGE", filtersTone: "warn",
      dataQuality: "PARTIAL",
      candidateStateBefore: "WATCHING",
      knew: ["Migration age 0h 18m (threshold 1h)", "ATH still forming", "Price fresh"],
      whatWouldChange: "Token becomes eligible after 1h migration age.",
    },
    {
      id: "PHX-12036",
      t: "21m", tAbs: "14:01:09",
      token: "BOME", tokenSub: "4nL2…XmQr", pair: "BOME / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "DEAD_CHART_PATTERN",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -95.0, filters: "RUG_PATTERN", filtersTone: "bad",
      dataQuality: "COMPLETE",
      candidateStateBefore: "DEAD",
      knew: ["Liquidity $5K (collapsed)", "Volume zero over 6h", "Holder distribution unhealthy"],
      whatWouldChange: "Dead chart pattern is terminal.",
    },
    {
      id: "PHX-12035",
      t: "26m", tAbs: "13:56:24",
      token: "PEPE", tokenSub: "5n4Q…aR2v", pair: "PEPE / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T1_DRAWDOWN_CONFIRMED",
      tier: "T1", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -68.2, filters: "ALL_PASS", filtersTone: "ok",
      dataQuality: "COMPLETE",
      candidateStateBefore: "NEAR_T1 · 3.2% away",
      knew: ["ATH $182M confirmed", "Drawdown crossed T1 threshold", "Volume $24M", "Bundle risk 0.08"],
      whatWouldChange: "Decision would flip only on price staleness or sudden liquidity drop.",
    },
    {
      id: "PHX-12034",
      t: "31m", tAbs: "13:51:50",
      token: "ANDY", tokenSub: "Hk4Q…2vRt", pair: "ANDY / SOL", pairQuote: "SOL",
      decision: "WATCH", reason: "BELOW_TIER_THRESHOLD",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -38.0, filters: "EVAL", filtersTone: "info",
      dataQuality: "COMPLETE",
      candidateStateBefore: "NEAR_T3 · 12.0% away",
      knew: ["Drawdown -38% is below T3 (-50%)", "Liquidity $2.9M", "ATH $45M confirmed"],
      whatWouldChange: "Token advances when drawdown crosses T3.",
    },
    {
      id: "PHX-12033",
      t: "38m", tAbs: "13:44:48",
      token: "NEIRO", tokenSub: "Vm8K…3pXr", pair: "NEIRO / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "LOW_LIQUIDITY",
      tier: "T3", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -71.0, filters: "LOW_LIQ", filtersTone: "bad",
      dataQuality: "PARTIAL",
      candidateStateBefore: "FILTER_BLOCKED",
      knew: ["Liquidity $128K (threshold $250K)", "Drawdown threshold met", "Volume inconsistent"],
      whatWouldChange: "Liquidity must recover above $250K for re-evaluation.",
    },
    {
      id: "PHX-12032",
      t: "42m", tAbs: "13:40:23",
      token: "GIGA", tokenSub: "Lq2N…8rXm", pair: "GIGA / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "LOW_LIQUIDITY",
      tier: "T2", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -55.8, filters: "LOW_LIQ", filtersTone: "bad",
      dataQuality: "COMPLETE",
      candidateStateBefore: "FILTER_BLOCKED",
      knew: ["Liquidity $182K", "Drawdown adequate for T2", "Volume declining"],
      whatWouldChange: "Liquidity threshold not met.",
    },
    {
      id: "PHX-12031",
      t: "51m", tAbs: "13:31:18",
      token: "BRETT", tokenSub: "9pBn…2KqL", pair: "BRETT / SOL", pairQuote: "SOL",
      decision: "OBSERVE_ONLY", reason: "POLICY_PENDING_REVIEW",
      tier: "T2", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -60.5, filters: "POLICY_REVIEW", filtersTone: "watching",
      dataQuality: "COMPLETE",
      candidateStateBefore: "WATCHING",
      knew: ["All gates clean", "Policy is under pending review", "Drawdown threshold met"],
      whatWouldChange: "Policy review must close before promotion.",
    },
    {
      id: "PHX-12030",
      t: "1h", tAbs: "13:21:32",
      token: "BORK", tokenSub: "3kQv…6JrN", pair: "BORK / SOL", pairQuote: "SOL",
      decision: "SKIP", reason: "FILTER_INCOMPLETE",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: null, filters: "FILTERS_INCOMPLETE", filtersTone: "warn",
      dataQuality: "FILTER_INCOMPLETE",
      candidateStateBefore: "WATCHING",
      knew: ["Bundle risk filter timed out", "Holder concentration filter unavailable", "Cannot evaluate fully"],
      whatWouldChange: "Filters must complete before re-evaluation.",
    },
    {
      id: "PHX-12029",
      t: "1h 12m", tAbs: "13:09:54",
      token: "GOAT", tokenSub: "X2pQ…4nMv", pair: "GOAT / SOL", pairQuote: "SOL",
      decision: "WOULD_ALERT", reason: "T2_DRAWDOWN_CONFIRMED",
      tier: "T2", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -55.2, filters: "ALL_PASS", filtersTone: "ok",
      dataQuality: "COMPLETE",
      candidateStateBefore: "NEAR_T2 · 0.2% away",
      knew: ["ATH $19M confirmed", "Drawdown crossed T2", "Liquidity $1.4M", "Filters clean"],
      whatWouldChange: "Stable WOULD_ALERT — no immediate flip risk.",
    },
    {
      id: "PHX-12028",
      t: "1h 22m", tAbs: "13:00:11",
      token: "MEW", tokenSub: "7vXk…N3qR", pair: "MEW / SOL", pairQuote: "SOL",
      decision: "WATCH", reason: "WAITING_FOR_PULLBACK",
      tier: "--", athState: "CONFIRMED", priceState: "FRESH",
      drawdown: -28.0, filters: "EVAL", filtersTone: "info",
      dataQuality: "COMPLETE",
      candidateStateBefore: "WATCHING",
      knew: ["Token still trending up", "Pullback yet to begin", "Tracking ATH"],
      whatWouldChange: "Pullback start triggers re-evaluation.",
    },
  ],
};

// ─── Derived counts (computed from whichever dataset is active) ──────
const decByType = (list, type) => list.filter((d) => d.decision === type).length;
const decByReason = (list, reason) => list.filter((d) => d.reason === reason).length;
const decByQuality = (list, q) => list.filter((d) => d.dataQuality === q).length;

function buildDecisionSummary(list) {
  return [
    { label: "Total Decisions", value: list.length, tone: "info" },
    { label: "Would Alert", value: decByType(list, "WOULD_ALERT"), tone: "called" },
    { label: "Sent", value: decByType(list, "SENT"), tone: "called" },
    { label: "Skipped", value: decByType(list, "SKIP"), tone: "bad" },
    { label: "Observe-only", value: decByType(list, "OBSERVE_ONLY"), tone: "watching" },
    { label: "Seeded / Candidate", value: decByType(list, "CANDIDATE"), tone: "ember" },
    { label: "Non-pump", value: decByReason(list, "NON_PUMP"), tone: "muted" },
    { label: "Market Unavailable", value: list.filter((d) => String(d.reason).includes("MARKET_UNAVAILABLE")).length, tone: "warn" },
    { label: "Partial Data", value: list.filter((d) => d.dataQuality !== "COMPLETE").length, tone: "warn" },
  ];
}

// Reason breakdown grouped by decision
function buildReasonBreakdown(list) {
  const groups = { WOULD_ALERT: {}, SENT: {}, SKIP: {}, OBSERVE_ONLY: {}, WATCH: {}, CANDIDATE: {} };
  list.forEach((d) => {
    if (!groups[d.decision]) groups[d.decision] = {};
    groups[d.decision][d.reason] = (groups[d.decision][d.reason] || 0) + 1;
  });
  return groups;
}

// Data quality breakdown
function buildDataQualityCounts(list) {
  return [
    { label: "Complete Data", key: "COMPLETE", value: decByQuality(list, "COMPLETE"), tone: "ok" },
    { label: "Partial Data", key: "PARTIAL", value: decByQuality(list, "PARTIAL"), tone: "warn" },
    { label: "Stale Data", key: "STALE", value: decByQuality(list, "STALE"), tone: "warn" },
    { label: "Missing ATH", key: "MISSING_ATH", value: decByQuality(list, "MISSING_ATH"), tone: "bad" },
    { label: "Missing LP", key: "MISSING_LP", value: decByQuality(list, "MISSING_LP"), tone: "bad" },
    { label: "Missing Price", key: "MISSING_PRICE", value: decByQuality(list, "MISSING_PRICE"), tone: "bad" },
    { label: "Filter Incomplete", key: "FILTER_INCOMPLETE", value: decByQuality(list, "FILTER_INCOMPLETE"), tone: "warn" },
    { label: "Outcome Pending", key: "OUTCOME_PENDING", value: list.length, tone: "muted" },
  ];
}

// ─── helpers ─────────────────────────────────────────────────────────
const decisionTone = {
  WOULD_ALERT: "called",
  SENT: "called",
  SKIP: "skipped",
  OBSERVE_ONLY: "watching",
  WATCH: "muted",
  CANDIDATE: "ember",
  PAPER_TRADE: "watching",
};
function DecisionPill({ value }) {
  return <span className={"pill pill-" + (decisionTone[value] || "muted")}>{value}</span>;
}

const qualityTone = {
  COMPLETE: "ok",
  PARTIAL: "warn",
  STALE: "warn",
  MISSING_ATH: "bad",
  MISSING_PRICE: "bad",
  FILTER_INCOMPLETE: "warn",
};
function QualityChip({ value }) {
  return <span className={"pill pill-" + (qualityTone[value] || "muted") + " pill-dim"}>{value}</span>;
}

function AthChip({ state }) {
  if (state === "CONFIRMED") return <span className="ath-chip ath-ok">● confirmed</span>;
  if (state === "UNKNOWN") return <span className="ath-chip ath-warn">○ unknown</span>;
  if (state === "NEW") return <span className="ath-chip ath-ember">◐ new</span>;
  return <span className="ath-chip ath-muted">{state}</span>;
}

function PriceChip({ state }) {
  if (state === "FRESH") return <span className="ath-chip ath-ok">● fresh</span>;
  if (state === "STALE") return <span className="ath-chip ath-warn">⚠ stale</span>;
  return <span className="ath-chip ath-muted">{state}</span>;
}

function explanationFor(d) {
  if (d.explanation) return d.explanation;
  if (d.decision === "SENT") {
    return `Phoenix sent a real private ping for ${d.token}. The send passed the dedupe ledger, the cap gate and the no-send-by-default transport guard before dispatch.`;
  }
  if (d.decision === "CANDIDATE" && d.reason === "SEEDED_PUMP_MIGRATION") {
    return `Phoenix seeded ${d.token} onto the watchlist after detecting a pump.fun migration. It will be rechecked for market context and dip-gate eligibility.`;
  }
  if (d.decision === "SKIP" && d.reason === "NON_PUMP") {
    return `Phoenix dropped ${d.token} because the mint is not a pump.fun migration. The fail-closed seeding boundary only admits pump migrations.`;
  }
  if (d.decision === "SKIP" && String(d.reason).includes("MARKET_UNAVAILABLE")) {
    return `Phoenix skipped ${d.token} because market context was incomplete at recheck time (MC, price and LP must all be present). The candidate stays on the watchlist for later rechecks.`;
  }
  if (d.decision === "WOULD_ALERT") {
    return `Phoenix would alert ${d.token} because ATH was confirmed at ${d.tier}, price was fresh, drawdown ${d.drawdown}% crossed the ${d.tier} threshold, and all observe-only filters were clean.`;
  }
  if (d.decision === "SKIP" && d.reason === "ATH_UNKNOWN") {
    return `Phoenix skipped ${d.token} because ATH was unknown at decision time. Without confirmed ATH, drawdown could not be trusted. Token remains eligible for reevaluation if ATH is later confirmed.`;
  }
  if (d.decision === "SKIP" && d.reason === "PRICE_STALE") {
    return `Phoenix skipped ${d.token} because the price feed was stale (>10s). Drawdown computed from a stale price cannot be trusted. Decision will be re-run on next fresh tick.`;
  }
  if (d.decision === "SKIP" && d.reason === "BUNDLE_RISK") {
    return `Phoenix skipped ${d.token} because bundle risk crossed the threshold. Drawdown and other gates were clean, but bundle risk is a hard skip filter.`;
  }
  if (d.decision === "SKIP" && d.reason === "LOW_LIQUIDITY") {
    return `Phoenix skipped ${d.token} because liquidity was below the required floor. Drawdown alone is not enough — Phoenix requires depth.`;
  }
  if (d.decision === "SKIP" && d.reason === "DEAD_CHART_PATTERN") {
    return `Phoenix skipped ${d.token}. The chart pattern matches abandonment / rug. The token is dropped from the candidate queue.`;
  }
  if (d.decision === "SKIP" && d.reason === "MIGRATION_TOO_FRESH") {
    return `Phoenix skipped ${d.token} because migration age is below the minimum window. New migrations need maturity before being eligible.`;
  }
  if (d.decision === "SKIP" && d.reason === "FILTER_INCOMPLETE") {
    return `Phoenix skipped ${d.token} because one or more filters did not return in time. Phoenix prefers conservative skip over partial evaluation.`;
  }
  if (d.decision === "OBSERVE_ONLY" && d.reason === "USDC_PAIR_OBSERVE_ONLY") {
    return `Phoenix marked ${d.token} observe-only because the pair is quoted in USDC, not SOL. USDC quotes are not promoted to alerts.`;
  }
  if (d.decision === "OBSERVE_ONLY" && d.reason === "POLICY_PENDING_REVIEW") {
    return `Phoenix marked ${d.token} observe-only because the governing policy is under pending review. Gates pass, but promotion is paused.`;
  }
  if (d.decision === "WATCH") {
    return `Phoenix is watching ${d.token}. Drawdown is below the tier threshold and the token is being tracked for further movement.`;
  }
  if (d.decision === "CANDIDATE") {
    return `Phoenix has entered ${d.token} into the candidate queue. Conditions are approaching a tier threshold but not yet met.`;
  }
  if (d.decision === "SKIP") {
    return `Phoenix skipped ${d.token}: ${d.reason}.`;
  }
  return "Decision recorded by Phoenix.";
}

// ─── Drawer ──────────────────────────────────────────────────────────
function DecisionDrawer({ decision, onClose }) {
  if (!decision) return null;
  return (
    <>
      <div className="cd-scrim" onClick={onClose} />
      <aside className="cd-drawer">
        <div className="cd-hd">
          <div>
            <div className="cd-eyebrow">Decision Detail · {decision.id}</div>
            <div className="cd-title">
              <span className="cd-sym">{decision.token}</span>
              <span className="cd-pair mono">{decision.pair}</span>
            </div>
            {decision.mint
              ? <FullCA value={decision.mint} />
              : <div className="cd-addr mono">{decision.tokenSub}</div>}
          </div>
          <button className="cd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="cd-stage-banner">
          <DecisionPill value={decision.decision} />
          <span className="cd-banner-target reason-chip mono">{decision.reason}</span>
          <span className="cd-banner-update meta-chunk">
            <span className="meta-k">at</span>
            <span className="meta-v">{decision.tAbs} · {decision.t} ago</span>
          </span>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Decision Context</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Decision type</span><b>{decision.decision}</b></div>
            <div className="cd-kv"><span>Reason code</span><b className="mono ember">{decision.reason}</b></div>
            <div className="cd-kv"><span>Tier</span><b className="mono">{decision.tier}</b></div>
            <div className="cd-kv"><span>Pair quote</span><b>{decision.pairQuote}</b></div>
            <div className="cd-kv"><span>ATH state</span><b><AthChip state={decision.athState} /></b></div>
            <div className="cd-kv"><span>Price state</span><b><PriceChip state={decision.priceState} /></b></div>
            <div className="cd-kv"><span>Drawdown</span><b className={decision.drawdown && decision.drawdown < -60 ? "ok mono" : "warn mono"}>{decision.drawdown != null ? decision.drawdown + "%" : "—"}</b></div>
            <div className="cd-kv"><span>Filters</span><b><Pill tone={decision.filtersTone}>{decision.filters}</Pill></b></div>
            <div className="cd-kv"><span>Data quality</span><b><QualityChip value={decision.dataQuality} /></b></div>
            <div className="cd-kv"><span>Pre-state</span><b className="mono">{decision.candidateStateBefore}</b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">What Phoenix knew at the time</div>
          <ul className="knew-list">
            {decision.knew.map((k, i) => (<li key={i}>{k}</li>))}
          </ul>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Why this decision</div>
          <p className="cd-note">{explanationFor(decision)}</p>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">What would have changed it</div>
          <p className="cd-note cd-note-warn">{decision.whatWouldChange}</p>
        </div>

        <div className="cd-foot">
          <span className="foot-mute">read-only · decision is final / replayable</span>
        </div>
      </aside>
    </>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function DecisionsPage() {
  const DecisionData = usePhxData("decisions", MOCK_DECISIONS);
  const live = usePhxLive();
  const [selected, setSelected] = React.useState(null);
  const [decisionFilter, setDecisionFilter] = React.useState("ALL");
  const [reasonFilter, setReasonFilter] = React.useState("ALL");
  const [tierFilter, setTierFilter] = React.useState("ALL");
  const [qualityFilter, setQualityFilter] = React.useState("ALL");
  const [pairFilter, setPairFilter] = React.useState("ALL");
  const [windowFilter, setWindowFilter] = React.useState("1h");
  const [sortMode, setSortMode] = React.useState("newest");

  const DecisionSummary = buildDecisionSummary(DecisionData.decisions);
  const DataQualityCounts = buildDataQualityCounts(DecisionData.decisions);

  let rows = [...DecisionData.decisions];
  if (decisionFilter !== "ALL") rows = rows.filter((d) => d.decision === decisionFilter);
  if (reasonFilter !== "ALL") rows = rows.filter((d) => d.reason === reasonFilter);
  if (tierFilter !== "ALL") rows = rows.filter((d) => d.tier === tierFilter);
  if (qualityFilter !== "ALL") rows = rows.filter((d) => d.dataQuality === qualityFilter);
  if (pairFilter !== "ALL") rows = rows.filter((d) => d.pairQuote === pairFilter);

  if (sortMode === "reason") rows.sort((a, b) => a.reason.localeCompare(b.reason));
  else if (sortMode === "tier") rows.sort((a, b) => (a.tier === "--" ? 99 : a.tier).toString().localeCompare((b.tier === "--" ? 99 : b.tier).toString()));
  else if (sortMode === "quality") rows.sort((a, b) => a.dataQuality.localeCompare(b.dataQuality));

  const breakdown = buildReasonBreakdown(DecisionData.decisions);

  return (
    <div className="live-page">
      {/* Header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Audit Trail</div>
          <h1 className="live-h1">
            Decisions
            <span className="live-pulse"><PulseDot /> {DecisionData.decisions.length} in ledger</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <Selector label="window" value={windowFilter} options={["15m","1h","6h","24h"]} onChange={setWindowFilter} />
          <Selector label="pair" value={pairFilter} options={["ALL","SOL","USDC","UNKNOWN"]} onChange={setPairFilter} />
          <Selector label="sort" value={sortMode} options={["newest","reason","tier","quality"]} onChange={setSortMode} />
        </div>
      </div>

      {/* Summary strip */}
      <div className="cand-summary dec-summary">
        {DecisionSummary.map((s, i) => (
          <div key={i} className={"cand-tile cand-tile-" + (s.tone || "info")}>
            <div className="cand-tile-val">{s.value}</div>
            <div className="cand-tile-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Quick filters row */}
      <div className="dec-filter-row">
        <div className="dec-filter-group">
          <span className="dec-filter-label">Decision</span>
          {["ALL","WOULD_ALERT","SKIP","OBSERVE_ONLY","WATCH","CANDIDATE"].map((f) => (
            <span key={f} className={"filter-chip " + (decisionFilter === f ? "active" : "")} onClick={() => setDecisionFilter(f)}>
              {f === "ALL" ? "All" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Reason</span>
          {["ALL","ATH_UNKNOWN","PRICE_STALE","BUNDLE_RISK","USDC_PAIR_OBSERVE_ONLY","DEAD_CHART_PATTERN","LOW_LIQUIDITY"].map((f) => (
            <span key={f} className={"filter-chip " + (reasonFilter === f ? "active" : "")} onClick={() => setReasonFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Tier</span>
          {["ALL","T1","T2","T3"].map((f) => (
            <span key={f} className={"filter-chip " + (tierFilter === f ? "active" : "")} onClick={() => setTierFilter(f)}>
              {f === "ALL" ? "Any" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Data</span>
          {["ALL","COMPLETE","PARTIAL"].map((f) => (
            <span key={f} className={"filter-chip " + (qualityFilter === f ? "active" : "")} onClick={() => setQualityFilter(f)}>
              {f === "ALL" ? "Any" : f.charAt(0) + f.slice(1).toLowerCase()}
            </span>
          ))}
        </div>
      </div>

      {/* Ledger Table */}
      <Card
        eyebrow="01 · Ledger"
        title="Decision Ledger"
        right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{rows.length}</span></span>}
      >
        <div className="tbl-wrap">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Time</th>
                <th>Token</th>
                <th>Pair</th>
                <th>Decision</th>
                <th>Reason</th>
                <th>Tier</th>
                <th>ATH</th>
                <th>Price</th>
                <th className="num">Drawdown</th>
                <th>Filters</th>
                <th>Data</th>
                <th className="num">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan="12"><div className="empty-state">No decisions in this view yet</div></td></tr>
              )}
              {rows.map((d) => (
                <tr key={d.id} onClick={() => setSelected(d)} className={selected && selected.id === d.id ? "row-active" : ""}>
                  <td className="dec-time">
                    <div className="dec-time-rel mono">{d.t}</div>
                    <div className="dec-time-abs mono mute">{d.tAbs}</div>
                  </td>
                  <td>
                    <div className="tok">
                      <span className="tok-sym">{d.token}</span>
                      <span className="tok-sub">{d.tokenSub}<CopyCA value={d.mint} /></span>
                    </div>
                  </td>
                  <td className="mono">{d.pair}</td>
                  <td><DecisionPill value={d.decision} /></td>
                  <td><span className="reason-chip mono">{d.reason}</span></td>
                  <td><span className={"tier tier-" + d.tier.toLowerCase().replace("--", "muted")}>{d.tier}</span></td>
                  <td><AthChip state={d.athState} /></td>
                  <td><PriceChip state={d.priceState} /></td>
                  <td className={"num mono " + (d.drawdown && d.drawdown < -70 ? "draw-bad" : d.drawdown && d.drawdown < -40 ? "draw-warn" : "draw-muted")}>
                    {d.drawdown != null ? d.drawdown.toFixed(1) + "%" : "—"}
                  </td>
                  <td><Pill tone={d.filtersTone} dim>{d.filters}</Pill></td>
                  <td><QualityChip value={d.dataQuality} /></td>
                  <td className="num"><span className="outcome-link mono">→ pending</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Bottom row: Reason breakdown + Data quality */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="02 · Reason Breakdown"
          title="Recent Decisions by Reason"
          right={<span className="meta-chunk"><span className="meta-k">window</span><span className="meta-v">{windowFilter}</span></span>}
        >
          <div className="reason-groups">
            {Object.entries(breakdown).map(([dec, reasons]) => {
              const entries = Object.entries(reasons);
              if (!entries.length) return null;
              return (
                <div key={dec} className="reason-group">
                  <div className="reason-group-hd">
                    <DecisionPill value={dec} />
                    <span className="reason-group-total mono">{entries.reduce((s,[,n])=>s+n,0)}</span>
                  </div>
                  <div className="reason-group-rows">
                    {entries.map(([r, n]) => (
                      <div key={r} className="reason-row" onClick={() => { setDecisionFilter(dec); setReasonFilter(r); }}>
                        <span className="reason-row-name mono">{r}</span>
                        <span className="reason-row-bar">
                          <span className="reason-row-fill" style={{ width: Math.min(100, n * 18) + "%" }} />
                        </span>
                        <span className="reason-row-count mono">{n}</span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card
          eyebrow="03 · Data Quality"
          title="What Phoenix had to work with"
          right={<span className="meta-chunk"><span className="meta-k">total</span><span className="meta-v">{DecisionData.decisions.length}</span></span>}
        >
          <div className="dq-list">
            {DataQualityCounts.map((q) => {
              const pct = DecisionData.decisions.length ? (q.value / DecisionData.decisions.length) * 100 : 0;
              return (
                <div key={q.key} className="dq-row">
                  <span className="dq-name">
                    <Dot tone={q.tone === "ok" ? "ok" : q.tone === "warn" ? "warn" : q.tone === "bad" ? "bad" : "muted"} />
                    <span>{q.label}</span>
                  </span>
                  <span className="dq-bar">
                    <span className={"dq-fill dq-fill-" + q.tone} style={{ width: pct + "%" }} />
                  </span>
                  <span className="dq-val mono">{q.value}</span>
                </div>
              );
            })}
          </div>
          <div className="dq-note">
            Use this to tell whether Phoenix is making bad calls because of <b>logic</b> or because of <b>missing / stale data</b>.
          </div>
        </Card>
      </div>

      <div className="live-foot">
        <span className="foot-mute">{live ? "artifact-backed · read-only" : "Front-end mock"} · click any row for full reasoning · ledger is read-only</span>
        <span className="foot-mute foot-pulse"><PulseDot /> decision stream</span>
      </div>

      <DecisionDrawer decision={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

// Compact selector
function Selector({ label, value, options, onChange }) {
  return (
    <span className="meta-chunk sel-chunk">
      <span className="meta-k">{label}</span>
      <select
        className="sel-native mono"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (<option key={o} value={o}>{o}</option>))}
      </select>
    </span>
  );
}

window.DecisionsPage = DecisionsPage;
Object.assign(window, { decisionTone, QualityChip, Selector, DecisionPill, AthChip, PriceChip });
