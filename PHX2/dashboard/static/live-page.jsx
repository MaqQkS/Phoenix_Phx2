// Phoenix — Live page (command center)
// Design-mock kept as fallback; real data comes from usePhxData("live", …)
// (PHX2 artifact adapter). No backend writes either way.

const MOCK_LIVE = {
  feedStatus: {
    bot: { label: "Phoenix Bot", value: "ONLINE", tone: "ok" },
    db: { label: "Live DB", value: "ACTIVE", tone: "ok" },
    provider: { label: "Provider", value: "Helius", tone: "ok" },
    priceApi: { label: "Price API", value: "Birdeye OK", tone: "ok" },
    discord: { label: "Discord Sink", value: "Ready", tone: "ok" },
    lastEvent: { label: "Last Event", value: "2s ago", tone: "info" },
    lastWrite: { label: "Last DB Write", value: "1s ago", tone: "info" },
    queue: { label: "Queue Pending", value: "3", tone: "info" },
    dedupe: { label: "Dedupe Status", value: "Active · 12,847", tone: "ok" },
    rawCap: { label: "Raw Capture", value: "Recording", tone: "ok" },
  },
  systemHealth: {
    providerHealth: { label: "Provider Health", value: "99.2%", tone: "ok" },
    rpcLatency: { label: "RPC Latency", value: "142ms", tone: "ok" },
    eventsMin: { label: "Events / min", value: "847", tone: "info" },
    malformed: { label: "Malformed Events", value: "0.03%", tone: "ok" },
    dedupeHits: { label: "Dedupe Hits", value: "21,394", tone: "info" },
    rawCaps: { label: "Raw Captures", value: "1,284 today", tone: "info" },
    failedNorm: { label: "Failed Normalizations", value: "12", tone: "warn" },
    priceFresh: { label: "Price Freshness", value: "0.8s", tone: "ok" },
    rateLimit: { label: "API Rate Limit", value: "84 / 120", tone: "info" },
    dispatch: { label: "Dispatch Status", value: "Enabled", tone: "ok" },
  },
  delta: [
    { label: "DEX Top 20 Seen", value: "17 / 20" },
    { label: "Called by Phoenix", value: "6", tone: "called" },
    { label: "Watched by Phoenix", value: "4", tone: "watching" },
    { label: "Skipped by Phoenix", value: "5", tone: "skipped" },
    { label: "Not Seen", value: "3", tone: "muted" },
    { label: "Phoenix Early", value: "2", tone: "ember" },
    { label: "DEX-only Movers", value: "3", tone: "muted" },
  ],
  liveFeed: [
    {
      token: "POPCAT",
      tokenSub: "9xK3…vB2p",
      pair: "POPCAT / SOL",
      lifecycle: "Active",
      mcap: "$48.2M",
      liq: "$1.20M",
      ath: "$52.1M",
      drawdown: "-7.5%",
      drawdownTone: "warn",
      tier: "T1",
      filters: "all pass",
      filtersTone: "ok",
      decision: "WOULD_ALERT",
      decisionTone: "called",
      updated: "3s",
    },
    {
      token: "WIF",
      tokenSub: "EKp…1F2h",
      pair: "WIF / USDC",
      lifecycle: "Observe",
      mcap: "$924K",
      liq: "$310K",
      ath: "$1.10M",
      drawdown: "-16.0%",
      drawdownTone: "warn",
      tier: "T2",
      filters: "USDC pair",
      filtersTone: "muted",
      decision: "OBSERVE_ONLY",
      decisionTone: "watching",
      updated: "12s",
    },
    {
      token: "BONK",
      tokenSub: "DezX…8mNq",
      pair: "BONK / SOL",
      lifecycle: "Pending",
      mcap: "$2.10M",
      liq: "$740K",
      ath: "—",
      drawdown: "—",
      drawdownTone: "muted",
      tier: "T3",
      filters: "ATH unknown",
      filtersTone: "warn",
      decision: "ATH_UNKNOWN → SKIP",
      decisionTone: "skipped",
      updated: "1m",
    },
    {
      token: "MOG",
      tokenSub: "Bx5p…RkLm",
      pair: "MOG / SOL",
      lifecycle: "Stale",
      mcap: "$880K",
      liq: "$410K",
      ath: "$1.40M",
      drawdown: "-37.1%",
      drawdownTone: "bad",
      tier: "T2",
      filters: "price stale",
      filtersTone: "warn",
      decision: "PRICE_STALE → SKIP",
      decisionTone: "skipped",
      updated: "4m",
    },
    {
      token: "DEGEN",
      tokenSub: "2sNv…UqWk",
      pair: "DEGEN / SOL",
      lifecycle: "Dead",
      mcap: "$24K",
      liq: "$8K",
      ath: "$980K",
      drawdown: "-97.6%",
      drawdownTone: "bad",
      tier: "T4",
      filters: "rug pattern",
      filtersTone: "bad",
      decision: "SKIP",
      decisionTone: "skipped",
      updated: "8m",
    },
    {
      token: "TURBO",
      tokenSub: "7q1v…J3xZ",
      pair: "TURBO / SOL",
      lifecycle: "Pending",
      mcap: "$612K",
      liq: "$190K",
      ath: "new",
      drawdown: "-2.8%",
      drawdownTone: "ok",
      tier: "T3",
      filters: "eval…",
      filtersTone: "info",
      decision: "CANDIDATE",
      decisionTone: "ember",
      updated: "14s",
    },
  ],
  dexTrending: [
    { rank: 1, token: "PEPE", pair: "PEPE / SOL", mcap: "$182M", vol: "$24.1M", trend: 18.2, status: "CALLED", reason: "Tier 1 alert sent" },
    { rank: 2, token: "WIF", pair: "WIF / SOL", mcap: "$94M", vol: "$11.4M", trend: 9.1, status: "WATCHING", reason: "On observe list" },
    { rank: 3, token: "BONK", pair: "BONK / SOL", mcap: "$52M", vol: "$7.2M", trend: 4.3, status: "STALE", reason: "Price feed lag 12s" },
    { rank: 4, token: "MOODENG", pair: "MOODENG / SOL", mcap: "$48M", vol: "$6.4M", trend: -3.1, status: "SKIPPED", reason: "Bundle risk 0.84" },
    { rank: 5, token: "POPCAT", pair: "POPCAT / SOL", mcap: "$42M", vol: "$5.1M", trend: 12.4, status: "CALLED", reason: "Tier 2 alert sent" },
    { rank: 6, token: "GIGA", pair: "GIGA / SOL", mcap: "$38M", vol: "$4.2M", trend: 7.0, status: "FILTERED", reason: "Liq < $250K" },
    { rank: 7, token: "BRETT", pair: "BRETT / SOL", mcap: "$34M", vol: "$3.8M", trend: -1.2, status: "WATCHING", reason: "Below tier threshold" },
    { rank: 8, token: "ANDY", pair: "ANDY / SOL", mcap: "$28M", vol: "$2.9M", trend: 22.6, status: "NOT SEEN", reason: "Outside Helius window" },
    { rank: 9, token: "PNUT", pair: "PNUT / SOL", mcap: "$24M", vol: "$2.4M", trend: 5.5, status: "CALLED", reason: "Tier 2, momentum +18%" },
    { rank: 10, token: "BOME", pair: "BOME / SOL", mcap: "$19M", vol: "$1.7M", trend: -8.4, status: "SKIPPED", reason: "Dead chart pattern" },
  ],
  decisions: [
    { t: "12s", type: "WOULD_ALERT", token: "POPCAT / SOL", reason: "Tier 1, all filters pass", tone: "called" },
    { t: "18s", type: "SKIP", token: "MOODENG / SOL", reason: "Bundle risk score 0.84", tone: "skipped" },
    { t: "24s", type: "OBSERVE_ONLY", token: "WIF / USDC", reason: "USDC quote pair, not SOL", tone: "watching" },
    { t: "41s", type: "WATCH", token: "TURBO / SOL", reason: "Within observe range, low liq", tone: "watching" },
    { t: "1m", type: "ATH_UNKNOWN", token: "BONK / SOL", reason: "Birdeye returned null ATH", tone: "warn" },
    { t: "2m", type: "PRICE_STALE", token: "MOG / SOL", reason: "Price feed > 10s old", tone: "warn" },
    { t: "4m", type: "WOULD_ALERT", token: "PNUT / SOL", reason: "Tier 2, momentum +18%", tone: "called" },
    { t: "5m", type: "BUNDLE_RISK", token: "CHEEMS / SOL", reason: "14 bundled wallets detected", tone: "bad" },
    { t: "8m", type: "USDC_PAIR_OBSERVE_ONLY", token: "USELESS / USDC", reason: "USDC pair gate", tone: "watching" },
    { t: "12m", type: "SKIP", token: "DEGEN / SOL", reason: "Liq drop > 60% in 5m", tone: "skipped" },
  ],
};

// ─── small primitives ────────────────────────────────────────────────
function Pill({ tone = "info", children, dim = false }) {
  return <span className={"pill pill-" + tone + (dim ? " pill-dim" : "")}>{children}</span>;
}

function Dot({ tone }) {
  return <span className={"dot dot-" + tone} />;
}

function Card({ title, eyebrow, children, right }) {
  return (
    <section className="lcard">
      <div className="lcard-hd">
        <div>
          {eyebrow && <div className="lcard-eyebrow">{eyebrow}</div>}
          <div className="lcard-title">{title}</div>
        </div>
        {right && <div className="lcard-right">{right}</div>}
      </div>
      <div className="lcard-body">{children}</div>
    </section>
  );
}

function MetricRow({ label, value, tone = "info" }) {
  return (
    <div className="metric-row">
      <span className="metric-lbl">
        <Dot tone={tone} />
        <span>{label}</span>
      </span>
      <span className={"metric-val metric-" + tone}>{value}</span>
    </div>
  );
}

function PulseDot() {
  return <span className="pulse-dot" aria-hidden="true" />;
}

// ─── Page ────────────────────────────────────────────────────────────
function LivePage() {
  const LiveData = usePhxData("live", MOCK_LIVE);
  const fs = LiveData.feedStatus;
  const sh = LiveData.systemHealth;
  const hdr = LiveData.header || {};

  return (
    <div className="live-page">
      {/* Page header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Command Center</div>
          <h1 className="live-h1">
            Live Feed
            <span className="live-pulse"><PulseDot /> {hdr.pulseLabel || "streaming"}</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <span className="meta-chunk"><span className="meta-k">env</span><span className="meta-v">{hdr.env || "mainnet"}</span></span>
          <span className="meta-chunk"><span className="meta-k">run</span><span className="meta-v">{hdr.node || "phx-01"}</span></span>
          <span className="meta-chunk"><span className="meta-k">uptime</span><span className="meta-v">{hdr.uptime || "14d 03h"}</span></span>
        </div>
      </div>

      {/* Row 1 — three status cards */}
      <div className="live-row live-row-3">
        <Card
          eyebrow="01 · Status"
          title="Bot / Feed Status"
          right={<Pill tone={hdr.overallTone || "ok"}>{hdr.overall || "All Systems Go"}</Pill>}
        >
          <div className="metric-grid">
            <MetricRow {...fs.bot} />
            <MetricRow {...fs.db} />
            <MetricRow {...fs.provider} />
            <MetricRow {...fs.priceApi} />
            <MetricRow {...fs.discord} />
            <MetricRow {...fs.lastEvent} />
            <MetricRow {...fs.lastWrite} />
            <MetricRow {...fs.queue} />
            <MetricRow {...fs.dedupe} />
            <MetricRow {...fs.rawCap} />
          </div>
        </Card>

        <Card
          eyebrow="02 · Health"
          title="System Health"
          right={<Pill tone="ok">nominal</Pill>}
        >
          <div className="metric-grid">
            <MetricRow {...sh.providerHealth} />
            <MetricRow {...sh.rpcLatency} />
            <MetricRow {...sh.eventsMin} />
            <MetricRow {...sh.malformed} />
            <MetricRow {...sh.dedupeHits} />
            <MetricRow {...sh.rawCaps} />
            <MetricRow {...sh.failedNorm} />
            <MetricRow {...sh.priceFresh} />
            <MetricRow {...sh.rateLimit} />
            <MetricRow {...sh.dispatch} />
          </div>
        </Card>

        <Card
          eyebrow={LiveData.deltaEyebrow || "05 · Delta"}
          title={LiveData.deltaTitle || "Phoenix × DEX Delta"}
          right={<span className="meta-chunk"><span className="meta-k">window</span><span className="meta-v">{LiveData.deltaWindow || "1h"}</span></span>}
        >
          <div className="delta-list">
            {LiveData.delta.map((d, i) => (
              <div key={i} className="delta-row">
                <span className="delta-lbl">{d.label}</span>
                <span className={"delta-val delta-" + (d.tone || "info")}>{d.value}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Row 2 — Phoenix Live Feed */}
      <Card
        eyebrow="03 · Feed"
        title="Phoenix Live Feed"
        right={
          <div className="card-actions">
            <span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{LiveData.liveFeed.length}</span></span>
            <span className="filter-chip active">All</span>
            <span className="filter-chip">Called</span>
            <span className="filter-chip">Skipped</span>
            <span className="filter-chip">Pending</span>
          </div>
        }
      >
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Token</th>
                <th>Pair</th>
                <th>Lifecycle</th>
                <th className="num">Market Cap</th>
                <th className="num">Liquidity</th>
                <th className="num">ATH</th>
                <th className="num">Drawdown</th>
                <th>Tier</th>
                <th>Filters</th>
                <th>Decision</th>
                <th className="num">Updated</th>
              </tr>
            </thead>
            <tbody>
              {LiveData.liveFeed.length === 0 && (
                <tr><td colSpan="11"><div className="empty-state">No watchlist rows yet — waiting for candidates</div></td></tr>
              )}
              {LiveData.liveFeed.map((r, i) => (
                <tr key={i}>
                  <td>
                    <div className="tok">
                      <span className="tok-sym">{r.token}</span>
                      <span className="tok-sub">{r.tokenSub}<CopyCA value={r.mint} /></span>
                    </div>
                  </td>
                  <td className="mono">{r.pair}</td>
                  <td><Pill tone={lifecycleTone(r.lifecycle)} dim>{r.lifecycle}</Pill></td>
                  <td className="num mono">{r.mcap}</td>
                  <td className="num mono">{r.liq}</td>
                  <td className="num mono">{r.ath}</td>
                  <td className={"num mono draw-" + r.drawdownTone}>{r.drawdown}</td>
                  <td><span className={"tier tier-" + r.tier.toLowerCase()}>{r.tier}</span></td>
                  <td><Pill tone={r.filtersTone} dim>{r.filters}</Pill></td>
                  <td><Pill tone={r.decisionTone}>{r.decision}</Pill></td>
                  <td className="num mono mute">{r.updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Row 3 — DEX Trending Comparison */}
      <Card
        eyebrow="04 · Comparison"
        title="DEX Trending vs Phoenix"
        right={
          <div className="card-actions">
            <span className="meta-chunk"><span className="meta-k">source</span><span className="meta-v">Dexscreener</span></span>
            <span className="meta-chunk"><span className="meta-k">refresh</span><span className="meta-v">15s</span></span>
          </div>
        }
      >
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th className="num">DEX#</th>
                <th>Token</th>
                <th>Pair</th>
                <th className="num">Market Cap</th>
                <th className="num">Volume</th>
                <th className="num">Trend</th>
                <th>Phoenix Status</th>
                <th>Phoenix Reason</th>
              </tr>
            </thead>
            <tbody>
              {LiveData.dexTrending.length === 0 && (
                <tr><td colSpan="8"><div className="empty-state">{LiveData.dexTrendingNote || "No DEX comparison data"}</div></td></tr>
              )}
              {LiveData.dexTrending.map((r, i) => (
                <tr key={i}>
                  <td className="num mono mute">#{r.rank}</td>
                  <td><span className="tok-sym">{r.token}</span></td>
                  <td className="mono">{r.pair}</td>
                  <td className="num mono">{r.mcap}</td>
                  <td className="num mono">{r.vol}</td>
                  <td className={"num mono " + (r.trend >= 0 ? "trend-up" : "trend-down")}>
                    {r.trend >= 0 ? "+" : ""}{r.trend.toFixed(1)}%
                  </td>
                  <td><Pill tone={statusTone(r.status)}>{r.status}</Pill></td>
                  <td className="reason">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Row 4 — Recent Decisions strip */}
      <Card
        eyebrow="06 · Decisions"
        title="Recent Decisions · Ugly Cases"
        right={<span className="meta-chunk"><span className="meta-k">last</span><span className="meta-v">15m</span></span>}
      >
        <div className="dec-strip">
          {LiveData.decisions.length === 0 && (
            <div className="empty-state">No decisions recorded yet</div>
          )}
          {LiveData.decisions.map((d, i) => (
            <div key={i} className={"dec-card dec-" + d.tone}>
              <div className="dec-top">
                <span className="dec-t">{d.t}</span>
                <span className={"dec-type dec-type-" + d.tone}>{d.type}</span>
              </div>
              <div className="dec-tok">{d.token}<CopyCA value={d.mint} /></div>
              <div className="dec-reason">{d.reason}</div>
            </div>
          ))}
        </div>
      </Card>

      <div className="live-foot">
        <span className="foot-mute">{LiveData.footLeft || "Front-end mock · no DB writes · no dispatch"}</span>
        <span className="foot-mute foot-pulse"><PulseDot /> {LiveData.footRight || "live data simulation"}</span>
      </div>
    </div>
  );
}

function lifecycleTone(v) {
  return {
    Active: "ok",
    Observe: "watching",
    Pending: "ember",
    Stale: "warn",
    Dead: "bad",
  }[v] || "muted";
}
function statusTone(v) {
  return {
    CALLED: "called",
    WATCHING: "watching",
    SKIPPED: "skipped",
    FILTERED: "muted",
    "NOT SEEN": "muted",
    STALE: "warn",
  }[v] || "info";
}

window.LivePage = LivePage;
Object.assign(window, { Card, Pill, Dot, MetricRow, PulseDot, lifecycleTone, statusTone });
