// Phoenix — Candidates page (pre-signal staging lane)
// Design-mock kept as fallback; real data from usePhxData("candidates", …).

const MOCK_CANDIDATES = {
  summary: [
    { label: "Total Candidates", value: 28, tone: "info" },
    { label: "Near Tier 1", value: 3, tone: "called" },
    { label: "Near Tier 2", value: 5, tone: "ember" },
    { label: "Waiting for ATH", value: 4, tone: "warn" },
    { label: "Price Stale", value: 2, tone: "warn" },
    { label: "USDC Observe-only", value: 3, tone: "watching" },
    { label: "Blocked by Filters", value: 6, tone: "bad" },
    { label: "Decaying / Dead", value: 5, tone: "muted" },
  ],
  queue: [
    {
      id: "popcat",
      token: "POPCAT", tokenSub: "9xK3…vB2p", pair: "POPCAT / SOL",
      stage: "NEAR_T1", lifecycle: "Active",
      mcap: "$48.2M", liq: "$1.20M",
      ath: "$52.1M", athState: "confirmed",
      drawdown: -58.4, distance: 1.6, distanceLabel: "1.6%", targetTier: "T1",
      blocker: "Needs deeper drawdown",
      nextCondition: "Needs -1.6% more drawdown",
      filters: "ALL_PASS", filtersTone: "ok",
      trend: -2.1, updated: "3s", timeInQueue: "4m",
      migrationAge: "4d 12h", priceFresh: "0.8s",
    },
    {
      id: "chill",
      token: "CHILL", tokenSub: "7Hp1…D9Mz", pair: "CHILL / SOL",
      stage: "NEAR_T2", lifecycle: "Active",
      mcap: "$3.8M", liq: "$580K",
      ath: "$6.9M", athState: "confirmed",
      drawdown: -45.1, distance: 4.9, distanceLabel: "4.9%", targetTier: "T2",
      blocker: "Drawdown approaching tier",
      nextCondition: "Needs -4.9% more drawdown",
      filters: "ALL_PASS", filtersTone: "ok",
      trend: -3.4, updated: "8s", timeInQueue: "12m",
      migrationAge: "2d 06h", priceFresh: "1.1s",
    },
    {
      id: "pnut",
      token: "PNUT", tokenSub: "3xVm…K7Lq", pair: "PNUT / SOL",
      stage: "NEAR_T2", lifecycle: "Active",
      mcap: "$24M", liq: "$2.1M",
      ath: "$41M", athState: "confirmed",
      drawdown: -43.2, distance: 6.8, distanceLabel: "6.8%", targetTier: "T2",
      blocker: "Drawdown approaching tier",
      nextCondition: "Needs -6.8% more drawdown",
      filters: "EVAL", filtersTone: "info",
      trend: -1.2, updated: "11s", timeInQueue: "41m",
      migrationAge: "12d 04h", priceFresh: "0.6s",
    },
    {
      id: "wif",
      token: "WIF", tokenSub: "EKp…1F2h", pair: "WIF / USDC",
      stage: "USDC_OBSERVE_ONLY", lifecycle: "Observe",
      mcap: "$924K", liq: "$310K",
      ath: "$1.10M", athState: "confirmed",
      drawdown: -66.0, distance: 0, distanceLabel: "met", targetTier: "T2",
      blocker: "USDC pair observe-only",
      nextCondition: "Needs SOL-pair calibration",
      filters: "USDC_PAIR", filtersTone: "watching",
      trend: 0.4, updated: "12s", timeInQueue: "2h 14m",
      migrationAge: "8h 22m", priceFresh: "0.9s",
    },
    {
      id: "andy",
      token: "ANDY", tokenSub: "Hk4Q…2vRt", pair: "ANDY / SOL",
      stage: "NEAR_T3", lifecycle: "Active",
      mcap: "$28M", liq: "$2.9M",
      ath: "$45M", athState: "confirmed",
      drawdown: -38.0, distance: 12.0, distanceLabel: "12.0%", targetTier: "T3",
      blocker: "Below tier threshold",
      nextCondition: "Needs tier threshold met (-12% more)",
      filters: "EVAL", filtersTone: "info",
      trend: 2.6, updated: "20s", timeInQueue: "1h 22m",
      migrationAge: "21d 09h", priceFresh: "1.4s",
    },
    {
      id: "turbo",
      token: "TURBO", tokenSub: "7q1v…J3xZ", pair: "TURBO / SOL",
      stage: "WATCHING", lifecycle: "Pending",
      mcap: "$612K", liq: "$190K",
      ath: "$1.10M", athState: "new",
      drawdown: -44.0, distance: 16.0, distanceLabel: "16.0%", targetTier: "T3",
      blocker: "Below tier threshold",
      nextCondition: "Needs migration age confirmation",
      filters: "EVAL", filtersTone: "info",
      trend: -0.8, updated: "14s", timeInQueue: "22s",
      migrationAge: "1h 14m", priceFresh: "0.7s",
    },
    {
      id: "bonk",
      token: "BONK", tokenSub: "DezX…8mNq", pair: "BONK / SOL",
      stage: "WAITING_FOR_ATH", lifecycle: "Pending",
      mcap: "$2.10M", liq: "$740K",
      ath: "—", athState: "unknown",
      drawdown: null, distance: null, distanceLabel: "—", targetTier: "T3",
      blocker: "ATH unknown",
      nextCondition: "Needs ATH confirmation",
      filters: "ATH_UNKNOWN", filtersTone: "warn",
      trend: 0.0, updated: "1m", timeInQueue: "3m",
      migrationAge: "3d 02h", priceFresh: "0.8s",
    },
    {
      id: "mog",
      token: "MOG", tokenSub: "Bx5p…RkLm", pair: "MOG / SOL",
      stage: "WAITING_FOR_PRICE", lifecycle: "Stale",
      mcap: "$880K", liq: "$410K",
      ath: "$1.40M", athState: "confirmed",
      drawdown: -37.1, distance: null, distanceLabel: "—", targetTier: "T2",
      blocker: "Price stale",
      nextCondition: "Needs fresh price feed",
      filters: "PRICE_STALE", filtersTone: "warn",
      trend: 0.0, updated: "4m", timeInQueue: "18m",
      migrationAge: "6d 18h", priceFresh: "14.2s",
    },
    {
      id: "cheems",
      token: "CHEEMS", tokenSub: "Cq8N…vK3R", pair: "CHEEMS / SOL",
      stage: "FILTER_BLOCKED", lifecycle: "Active",
      mcap: "$5.2M", liq: "$680K",
      ath: "$14M", athState: "confirmed",
      drawdown: -62.5, distance: 0, distanceLabel: "met", targetTier: "T2",
      blocker: "Bundle risk score 0.84",
      nextCondition: "Needs bundle risk cleared",
      filters: "BUNDLE_RISK", filtersTone: "bad",
      trend: -4.2, updated: "32s", timeInQueue: "1h 06m",
      migrationAge: "5d 08h", priceFresh: "0.9s",
    },
    {
      id: "moodeng",
      token: "MOODENG", tokenSub: "9vRk…X2pN", pair: "MOODENG / SOL",
      stage: "DECAYING", lifecycle: "Active",
      mcap: "$8.4M", liq: "$420K",
      ath: "$29M", athState: "confirmed",
      drawdown: -71.0, distance: 0, distanceLabel: "met", targetTier: "T2",
      blocker: "Volume decay > 60%",
      nextCondition: "Needs liquidity recovery",
      filters: "LIQ_DROP", filtersTone: "bad",
      trend: -7.8, updated: "45s", timeInQueue: "2h 38m",
      migrationAge: "9d 14h", priceFresh: "1.0s",
    },
    {
      id: "degen",
      token: "DEGEN", tokenSub: "2sNv…UqWk", pair: "DEGEN / SOL",
      stage: "DEAD", lifecycle: "Dead",
      mcap: "$24K", liq: "$8K",
      ath: "$980K", athState: "confirmed",
      drawdown: -97.6, distance: 0, distanceLabel: "met", targetTier: "T3",
      blocker: "Dead chart pattern",
      nextCondition: "Invalidated — dropping from queue",
      filters: "RUG_PATTERN", filtersTone: "bad",
      trend: -12.4, updated: "8m", timeInQueue: "4h 12m",
      migrationAge: "18d 02h", priceFresh: "2.1s",
    },
    {
      id: "bome",
      token: "BOME", tokenSub: "4nL2…XmQr", pair: "BOME / SOL",
      stage: "DEAD", lifecycle: "Dead",
      mcap: "$19K", liq: "$5K",
      ath: "$1.4M", athState: "confirmed",
      drawdown: -95.0, distance: 0, distanceLabel: "met", targetTier: "T3",
      blocker: "Dead chart pattern",
      nextCondition: "Invalidated — dropping from queue",
      filters: "RUG_PATTERN", filtersTone: "bad",
      trend: -8.4, updated: "11m", timeInQueue: "6h 02m",
      migrationAge: "24d 11h", priceFresh: "1.8s",
    },
  ],
};

// Near-tier rows: tokens closest to tier (smallest non-null distance, sorted asc)
function nearTierRowsOf(queue) {
  return queue
    .filter((c) => c.distance != null && c.stage.startsWith("NEAR_"))
    .sort((a, b) => a.distance - b.distance);
}

// Blocker groups — real rows carry an explicit blockerGroup label; the design
// mock is grouped via its legacy filter codes.
const LEGACY_BLOCKER_GROUPS = {
  ATH_UNKNOWN: "ATH Unknown",
  PRICE_STALE: "Price Stale",
  USDC_PAIR: "USDC Observe-only",
  BUNDLE_RISK: "Bundle Risk",
  LIQ_DROP: "Low Liquidity",
  RUG_PATTERN: "Dead / Rug Pattern",
};
function blockerGroupsOf(queue) {
  const groups = {};
  queue.forEach((c) => {
    const name = c.blockerGroup || LEGACY_BLOCKER_GROUPS[c.filters];
    if (!name) return;
    if (!groups[name]) groups[name] = [];
    groups[name].push(c);
  });
  return groups;
}

// Timeline templates per candidate
function timelineFor(c) {
  const base = [
    { label: "First seen", t: c.migrationAge + " ago", state: "done" },
    { label: "Migrated", t: c.migrationAge + " ago", state: "done" },
  ];
  if (c.athState === "unknown") {
    base.push({ label: "ATH detection", t: "pending", state: "current" });
    base.push({ label: "Pullback", t: "—", state: "future" });
    base.push({ label: "Candidate queue", t: "entered " + c.updated + " ago", state: "current" });
    base.push({ label: "Near tier", t: "blocked: ATH unknown", state: "blocked" });
    return base;
  }
  base.push({ label: "ATH detected", t: c.ath, state: "done" });
  base.push({ label: "Pullback started", t: c.drawdown ? c.drawdown.toFixed(1) + "%" : "—", state: "done" });
  base.push({ label: "Candidate queue", t: "in queue " + c.updated, state: "done" });
  if (c.stage === "DEAD") {
    base.push({ label: "Dead", t: "rug pattern detected", state: "blocked" });
  } else if (c.stage === "DECAYING") {
    base.push({ label: "Decaying", t: "volume decay > 60%", state: "blocked" });
  } else if (c.stage === "FILTER_BLOCKED") {
    base.push({ label: "Blocked", t: c.blocker, state: "blocked" });
  } else if (c.stage === "USDC_OBSERVE_ONLY") {
    base.push({ label: "Observe-only", t: "USDC quote pair", state: "current" });
  } else if (c.stage === "WAITING_FOR_PRICE") {
    base.push({ label: "Waiting", t: "price stale " + c.priceFresh, state: "current" });
  } else if (c.stage.startsWith("NEAR_")) {
    base.push({ label: "Near " + c.targetTier, t: c.distanceLabel + " away", state: "current" });
    base.push({ label: "Signal", t: "pending threshold", state: "future" });
  } else {
    base.push({ label: "Watching", t: c.blocker, state: "current" });
    base.push({ label: "Near tier", t: c.distanceLabel + " away", state: "future" });
  }
  return base;
}

// Explanations — real artifact rows carry their own reasoning snapshot.
function explanationFor(c) {
  if (c.explanation) return c.explanation;
  if (c.stage === "NEAR_T1") {
    return `Not a signal yet: ATH is confirmed, but drawdown is only ${c.drawdown}%. Tier 1 requires deeper pullback. Liquidity and filters are currently acceptable.`;
  }
  if (c.stage === "NEAR_T2") {
    return `Not a signal yet: drawdown ${c.drawdown}% is ${c.distanceLabel} from the Tier 2 threshold. Filters are passing. Watching for further pullback.`;
  }
  if (c.stage === "NEAR_T3") {
    return `Not a signal yet: drawdown ${c.drawdown}% is ${c.distanceLabel} below the Tier 3 threshold. Still evaluating filter context.`;
  }
  if (c.stage === "WAITING_FOR_ATH") {
    return `Not a signal yet: ATH could not be confirmed from the price source. Phoenix cannot evaluate drawdown without a verified ATH.`;
  }
  if (c.stage === "WAITING_FOR_PRICE") {
    return `Not a signal yet: price freshness is ${c.priceFresh}, above the staleness threshold. Decision deferred until feed catches up.`;
  }
  if (c.stage === "USDC_OBSERVE_ONLY") {
    return `Not a signal: pair is quoted in USDC, not SOL. Phoenix records observe-only and will not promote USDC quotes to alerts.`;
  }
  if (c.stage === "FILTER_BLOCKED") {
    return `Filter-blocked: ${c.blocker}. Drawdown threshold is met but the filter context disqualifies this candidate.`;
  }
  if (c.stage === "DECAYING") {
    return `Decaying: drawdown threshold met, but liquidity and volume are collapsing. Phoenix will not call a token that is structurally breaking down.`;
  }
  if (c.stage === "DEAD") {
    return `Dead: chart pattern matches rug / abandonment. Candidate retained briefly for audit, then dropped from queue.`;
  }
  return `Watching: candidate is in the staging lane while Phoenix evaluates whether it can become a signal.`;
}

// ─── primitives ──────────────────────────────────────────────────────
const stageMeta = {
  WATCHING: { tone: "watching", label: "WATCHING" },
  NEAR_T1: { tone: "called", label: "NEAR_T1" },
  NEAR_T2: { tone: "ember", label: "NEAR_T2" },
  NEAR_T3: { tone: "ember", label: "NEAR_T3" },
  WAITING_FOR_ATH: { tone: "warn", label: "WAITING_FOR_ATH" },
  WAITING_FOR_PRICE: { tone: "warn", label: "WAITING_FOR_PRICE" },
  USDC_OBSERVE_ONLY: { tone: "watching", label: "USDC_OBSERVE_ONLY" },
  FILTER_BLOCKED: { tone: "bad", label: "FILTER_BLOCKED" },
  DECAYING: { tone: "bad", label: "DECAYING" },
  DEAD: { tone: "bad", label: "DEAD" },
};

function StagePill({ stage }) {
  const m = stageMeta[stage] || { tone: "muted", label: stage };
  return <span className={"pill pill-" + m.tone}>{m.label}</span>;
}

function DistanceBar({ distance, label }) {
  if (distance == null) return <span className="dist-na">—</span>;
  if (distance === 0) return <span className="dist-met">MET</span>;
  // Smaller distance = closer = more filled
  const pct = Math.max(0, Math.min(100, 100 - distance * 5)); // 0% dist → 100, 20% dist → 0
  return (
    <span className="dist-wrap">
      <span className="dist-track">
        <span className="dist-fill" style={{ width: pct + "%" }} />
      </span>
      <span className="dist-num mono">{label}</span>
    </span>
  );
}

function TrendSpark({ value }) {
  if (value == null) return <span className="trend-cell mono trend-flat">—</span>;
  const up = value > 0.2;
  const down = value < -0.2;
  const cls = up ? "trend-up" : down ? "trend-down" : "trend-flat";
  const arrow = up ? "▲" : down ? "▼" : "·";
  return (
    <span className={"trend-cell mono " + cls}>
      <span className="trend-arrow">{arrow}</span>
      {value > 0 ? "+" : ""}{value.toFixed(1)}%
    </span>
  );
}

// Momentum: Phoenix-native label + delta
function momentumOf(value) {
  if (value >= 2.0)   return { label: "Improving",     tone: "ok" };
  if (value <= -10.0) return { label: "Dead",          tone: "bad" };
  if (value <= -5.0)  return { label: "Breaking Down", tone: "bad" };
  if (value <= -1.5)  return { label: "Decaying",      tone: "warn" };
  return                     { label: "Flat",          tone: "muted" };
}
function Momentum({ value }) {
  if (value == null) {
    return (
      <span className="mom-cell mom-muted">
        <span className="mom-lbl">—</span>
      </span>
    );
  }
  const m = momentumOf(value);
  return (
    <span className={"mom-cell mom-" + m.tone}>
      <span className="mom-lbl">{m.label}</span>
      <span className="mom-delta mono">{value > 0 ? "+" : ""}{value.toFixed(1)}%</span>
    </span>
  );
}

// Stage ordering: NEAR first → WATCHING → WAITING → USDC_OBSERVE → FILTER_BLOCKED → DECAYING → DEAD
const STAGE_ORDER = {
  NEAR_T1: 0, NEAR_T2: 1, NEAR_T3: 2,
  WATCHING: 3,
  WAITING_FOR_ATH: 4, WAITING_FOR_PRICE: 5,
  USDC_OBSERVE_ONLY: 6,
  FILTER_BLOCKED: 7,
  DECAYING: 8,
  DEAD: 9,
};
function sortQueue(rows) {
  return [...rows].sort((a, b) => {
    const sa = STAGE_ORDER[a.stage] ?? 99;
    const sb = STAGE_ORDER[b.stage] ?? 99;
    if (sa !== sb) return sa - sb;
    // within NEAR_*, closer distance first
    if (a.distance != null && b.distance != null) return a.distance - b.distance;
    return 0;
  });
}

// ─── Drawer ──────────────────────────────────────────────────────────
function CandidateDrawer({ candidate, onClose }) {
  if (!candidate) return null;
  const tl = timelineFor(candidate);
  const m = stageMeta[candidate.stage] || { tone: "muted", label: candidate.stage };
  return (
    <>
      <div className="cd-scrim" onClick={onClose} />
      <aside className="cd-drawer">
        <div className="cd-hd">
          <div>
            <div className="cd-eyebrow">Candidate Detail</div>
            <div className="cd-title">
              <span className="cd-sym">{candidate.token}</span>
              <span className="cd-pair mono">{candidate.pair}</span>
            </div>
            {candidate.mint
              ? <FullCA value={candidate.mint} />
              : <div className="cd-addr mono">{candidate.tokenSub}</div>}
          </div>
          <button className="cd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="cd-stage-banner">
          <span className={"pill pill-" + m.tone}>{m.label}</span>
          <span className="cd-banner-target">target <b>{candidate.targetTier}</b></span>
          <span className="cd-banner-update meta-chunk">
            <span className="meta-k">upd</span>
            <span className="meta-v">{candidate.updated}</span>
          </span>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Identity</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Pair type</span><b>{candidate.pair.includes("USDC") ? "USDC quote" : "SOL quote"}</b></div>
            <div className="cd-kv"><span>Lifecycle</span><b>{candidate.lifecycle}</b></div>
            <div className="cd-kv"><span>Migration age</span><b>{candidate.migrationAge}</b></div>
            <div className="cd-kv"><span>Time in queue</span><b className="mono ember">{candidate.timeInQueue}</b></div>
            <div className="cd-kv"><span>Price freshness</span><b className={parseFloat(candidate.priceFresh) > 5 ? "warn" : "ok"}>{candidate.priceFresh}</b></div>
            <div className="cd-kv"><span>Momentum</span><b><Momentum value={candidate.trend} /></b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Tier Status</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>ATH state</span><b>{candidate.athState === "confirmed" ? "Confirmed " + candidate.ath : candidate.athState === "unknown" ? "Unknown" : "New (" + candidate.ath + ")"}</b></div>
            <div className="cd-kv"><span>Current drawdown</span><b className={candidate.drawdown && candidate.drawdown < -50 ? "ok" : "warn"}>{candidate.drawdown != null ? candidate.drawdown + "%" : "—"}</b></div>
            <div className="cd-kv"><span>Distance to {candidate.targetTier}</span><b>{candidate.distanceLabel}</b></div>
            <div className="cd-kv"><span>Market cap</span><b className="mono">{candidate.mcap}</b></div>
            <div className="cd-kv"><span>Liquidity</span><b className="mono">{candidate.liq}</b></div>
            <div className="cd-kv"><span>Trend (5m)</span><b><TrendSpark value={candidate.trend} /></b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Blocker → Next Required</div>
          <div className="cd-blocker">
            <div className="cd-blocker-icon">!</div>
            <div className="cd-blocker-body">
              <div className="cd-blocker-title">{candidate.blocker}</div>
              <div className="cd-blocker-next">
                <span className="cd-blocker-next-arrow">→</span>
                <span>{candidate.nextCondition}</span>
              </div>
              <div className="cd-blocker-filter">
                <Pill tone={candidate.filtersTone}>{candidate.filters}</Pill>
              </div>
            </div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Timeline</div>
          <ol className="cd-timeline">
            {tl.map((s, i) => (
              <li key={i} className={"cd-step cd-step-" + s.state}>
                <span className="cd-step-dot" />
                <div className="cd-step-body">
                  <div className="cd-step-label">{s.label}</div>
                  <div className="cd-step-t">{s.t}</div>
                </div>
              </li>
            ))}
          </ol>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Why this is not a signal yet</div>
          <p className="cd-note">{explanationFor(candidate)}</p>
        </div>

        <div className="cd-foot">
          <span className="foot-mute">read-only · no actions available</span>
        </div>
      </aside>
    </>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function CandidatesPage() {
  const CandidateData = usePhxData("candidates", MOCK_CANDIDATES);
  const live = usePhxLive();
  const [selected, setSelected] = React.useState(null);
  const [stageFilter, setStageFilter] = React.useState("ALL");
  const [hideDead, setHideDead] = React.useState(true);

  const nearTierRows = nearTierRowsOf(CandidateData.queue);
  const blockerGroups = blockerGroupsOf(CandidateData.queue);
  const hm = CandidateData.headerMeta || {};
  const baseRows = sortQueue(CandidateData.queue);

  let filtered = baseRows;
  if (stageFilter !== "ALL") {
    filtered = baseRows.filter((c) => {
      if (stageFilter === "NEAR") return c.stage.startsWith("NEAR_");
      if (stageFilter === "WAITING") return c.stage.startsWith("WAITING_");
      if (stageFilter === "BLOCKED") return c.stage === "FILTER_BLOCKED" || c.stage === "USDC_OBSERVE_ONLY";
      if (stageFilter === "DEAD") return c.stage === "DECAYING" || c.stage === "DEAD";
      return true;
    });
  }
  if (hideDead && stageFilter !== "DEAD") {
    filtered = filtered.filter((c) => c.stage !== "DEAD");
  }

  const deadCount = baseRows.filter((c) => c.stage === "DEAD").length;

  return (
    <div className="live-page">
      {/* Header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Staging Lane</div>
          <h1 className="live-h1">
            Candidates
            <span className="live-pulse"><PulseDot /> {CandidateData.queue.length} in queue</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <span className="meta-chunk"><span className="meta-k">window</span><span className="meta-v">{hm.window || "15m"}</span></span>
          <span className="meta-chunk"><span className="meta-k">sort</span><span className="meta-v">{hm.sort || "distance"}</span></span>
          <span className="meta-chunk"><span className="meta-k">refresh</span><span className="meta-v">{hm.refresh || "2s"}</span></span>
        </div>
      </div>

      {/* Summary strip */}
      <div className="cand-summary">
        {CandidateData.summary.map((s, i) => (
          <div key={i} className={"cand-tile cand-tile-" + (s.tone || "info")}>
            <div className="cand-tile-val">{s.value}</div>
            <div className="cand-tile-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Candidate Queue Table */}
      <Card
        eyebrow="01 · Queue"
        title="Candidate Queue"
        right={
          <div className="card-actions">
            <span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{filtered.length}</span></span>
            {["ALL", "NEAR", "WAITING", "BLOCKED", "DEAD"].map((f) => (
              <span
                key={f}
                className={"filter-chip " + (stageFilter === f ? "active" : "")}
                onClick={() => setStageFilter(f)}
              >{f === "ALL" ? "All" : f.charAt(0) + f.slice(1).toLowerCase()}</span>
            ))}
            <span
              className={"filter-chip filter-toggle " + (hideDead ? "" : "active")}
              onClick={() => setHideDead(!hideDead)}
              title={hideDead ? "Show dead tokens in the main queue" : "Hide dead tokens from the main queue"}
            >
              {hideDead ? `✕ dead hidden (${deadCount})` : `✓ dead shown`}
            </span>
          </div>
        }
      >
        <div className="tbl-wrap">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Token</th>
                <th>Pair</th>
                <th>Stage</th>
                <th>Life</th>
                <th className="num">Market Cap</th>
                <th className="num">Liquidity</th>
                <th>ATH</th>
                <th className="num">Drawdown</th>
                <th>Distance</th>
                <th>Blocker / Next Required</th>
                <th>Filters</th>
                <th>Risk</th>
                <th>Momentum</th>
                <th className="num">In Queue</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 && (
                <tr><td colSpan="14"><div className="empty-state">No candidates in this view yet</div></td></tr>
              )}
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  onClick={() => setSelected(c)}
                  className={
                    (selected && selected.id === c.id ? "row-active " : "") +
                    (c.stage === "DEAD" ? "row-dead " : "") +
                    (c.stage === "DECAYING" ? "row-decaying " : "")
                  }
                >
                  <td>
                    <div className="tok">
                      <span className="tok-sym">{c.token}</span>
                      <span className="tok-sub">{c.tokenSub}<CopyCA value={c.mint} /></span>
                    </div>
                  </td>
                  <td className="mono">{c.pair}</td>
                  <td><StagePill stage={c.stage} /></td>
                  <td><Pill tone={lifecycleTone(c.lifecycle)} dim>{c.lifecycle}</Pill></td>
                  <td className="num mono">{c.mcap}</td>
                  <td className="num mono">{c.liq}</td>
                  <td className="mono mute">
                    {c.athState === "confirmed" ? c.ath : c.athState === "unknown" ? <span className="warn">unknown</span> : <span className="ember">new</span>}
                  </td>
                  <td className={"num mono " + (c.drawdown && c.drawdown < -70 ? "draw-bad" : c.drawdown && c.drawdown < -40 ? "draw-warn" : "draw-muted")}>
                    {c.drawdown != null ? c.drawdown.toFixed(1) + "%" : "—"}
                  </td>
                  <td><DistanceBar distance={c.distance} label={c.distanceLabel} /></td>
                  <td>
                    <div className="blk-cell">
                      <div className="blk-now">{c.blocker}</div>
                      <div className="blk-next">
                        <span className="blk-next-arrow">→</span>
                        <span>{c.nextCondition}</span>
                      </div>
                    </div>
                  </td>
                  <td><Pill tone={c.filtersTone} dim>{c.filters}</Pill></td>
                  <td title={(c.riskReasons || []).join(", ")}>
                    <Pill tone={c.riskTone || "muted"} dim>{c.risk || "?"}</Pill>
                  </td>
                  <td><Momentum value={c.trend} /></td>
                  <td className="num mono mute">{c.timeInQueue}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Row: Near-Tier + Blocked */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="02 · Near-Tier Watch"
          title="Closest to Alert"
          right={<span className="meta-chunk"><span className="meta-k">sorted</span><span className="meta-v">↑ distance</span></span>}
        >
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Token</th>
                  <th className="num">Drawdown</th>
                  <th className="num">Needed</th>
                  <th className="num">Distance</th>
                  <th>ATH</th>
                  <th>Price</th>
                  <th>Est. Status</th>
                </tr>
              </thead>
              <tbody>
                {nearTierRows.length === 0 && (
                  <tr><td colSpan="7"><div className="empty-state">No candidates near a tier threshold yet</div></td></tr>
                )}
                {nearTierRows.map((c) => {
                  const needed = c.drawdown - c.distance;
                  return (
                    <tr key={c.id} onClick={() => setSelected(c)} className="tbl-clickable">
                      <td><span className="tok-sym">{c.token}</span> <span className="mono mute">{c.pair.split(" / ")[1]}</span><CopyCA value={c.mint} /></td>
                      <td className="num mono draw-warn">{c.drawdown.toFixed(1)}%</td>
                      <td className="num mono mute">{needed.toFixed(1)}%</td>
                      <td className="num mono ember">{c.distanceLabel} away</td>
                      <td><Pill tone="ok" dim>confirmed</Pill></td>
                      <td><Pill tone="ok" dim>fresh</Pill></td>
                      <td><StagePill stage={c.stage} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          eyebrow="03 · Blocked Candidates"
          title="Grouped by Blocker"
          right={<span className="meta-chunk"><span className="meta-k">groups</span><span className="meta-v">{Object.values(blockerGroups).filter(g => g.length).length}</span></span>}
        >
          <div className="block-groups">
            {Object.values(blockerGroups).every((g) => !g.length) && (
              <div className="empty-state">No blocked candidates</div>
            )}
            {Object.entries(blockerGroups).map(([name, rows]) => {
              if (!rows.length) return null;
              return (
                <div key={name} className="block-group">
                  <div className="block-group-hd">
                    <span className="block-group-name">{name}</span>
                    <span className="block-group-count">{rows.length}</span>
                  </div>
                  <div className="block-group-rows">
                    {rows.map((c) => (
                      <div key={c.id} className="block-row" onClick={() => setSelected(c)}>
                        <div>
                          <div className="block-row-tok">{c.token} <span className="mono mute">/ {c.pair.split(" / ")[1]}</span><CopyCA value={c.mint} /></div>
                          <div className="block-row-state">last good: {c.athState === "confirmed" ? "ATH " + c.ath : "—"}</div>
                        </div>
                        <div className="block-row-meta">
                          <Pill tone={c.filtersTone} dim>{c.filters}</Pill>
                          <span className="block-row-t mono">{c.updated}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <div className="live-foot">
        <span className="foot-mute">{live ? "artifact-backed · read-only" : "Front-end mock"} · click any row for detail</span>
        <span className="foot-mute foot-pulse"><PulseDot /> staging lane</span>
      </div>

      <CandidateDrawer candidate={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

window.CandidatesPage = CandidatesPage;
