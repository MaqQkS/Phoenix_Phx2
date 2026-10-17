// Phoenix — Paper Trading / Live Pings page (PHX2 artifact-backed).
// Built from the existing design primitives (Card / Pill / MetricRow / tiles /
// tbl). READ-ONLY: renders producer + paper artifacts; no actions exist here.

const MOCK_PAPER = {
  system: {
    producer: {
      status: "UNKNOWN", tone: "muted", heartbeat_age: "—", last_update_utc: "—",
      run_id: "demo_run", out_dir: "(mock) producer out dir", stop_reason: "—",
      mode: "FREE_TIER_PRIVATE_DISCORD", tick: 0, interrupted: false,
    },
    paper: {
      status: "UNKNOWN", tone: "muted", heartbeat_age: "—", last_update_utc: "—",
      run_id: "demo_paper", out_dir: "(mock) paper out dir", uptime: "—",
      snapshots_processed: 0, last_error: "—", last_skip: "—", watch_inputs: [],
    },
  },
  discord: {
    enabled: "UNKNOWN", enabled_tone: "muted", last_ping_result: "UNKNOWN",
    last_ping_tone: "muted", outcome: "—", private_ping_count: 0,
    would_ping_count: 0, send_attempts: 0, sent_ok_count: 0, max_sends_per_run: 0,
    dedupe_suppressed_total: 0, ledger_lines: null, ledger_delta_total: null,
    last_would_ping: "—", last_sent_ping: "—", last_no_ping_reason: "—",
    routing_note: "mock", public_or_subscriber_routing: false,
  },
  discovery: {
    ws_notifications_seen: 0, ws_notifications_cap: 0, seed_windows: 0,
    seed_windows_cap: 0, candidate_count: 0, candidate_cap: 0, watch_total: 0,
    watch_by_status: {}, watching_now: 0, dropped_non_pump: 0,
    market_requests: 0, market_requests_cap: 0, market_http_429: 0,
    gettransaction_fetches: 0, gettransaction_cap: 0, rpc_429_count: 0,
    rpc_429_cap: 0, rpc_errors_total: 0, budget_stop_reason: null,
    windows_blocked_by_budget: 0, reseeds: 0, ticks: 0,
    axiom_pass_total: null, axiom_fail_total: null, no_send_reasons: {},
    remaining: {}, market_pairs_calls: null, market_ohlcv_calls: null,
    market_cache_hits: null,
  },
  credit_panel: {
    manual_entry: true, auto_read: false, entry_provided: false,
    discovery_mode: "—", raw_ws_msg_count: 0, polling_tx_count: 0,
    market_http_calls: 0, gettransaction_fetches: 0, sent_pings: 0,
    credits_before: null, credits_after: null, credits_used: null,
    credits_per_hour: null, credits_per_day: null, credits_per_ping: null,
    days_to_exhaust: null, as_of_utc: null,
    raw_ws_note: "raw WS messages — not Helius credits",
    source_note: "Mock — start PHX2/dashboard/server.py for real artifacts.",
    entry_hint: "Set config.json helius_credits {before, after, window_seconds}.",
  },
  trading: {
    open_positions: 0, closed_positions: 0, realized_pnl: "—", unrealized_pnl: "—",
    total_pnl: "—", win_rate: "—", best_trade: "—", worst_trade: "—",
    skip_reasons: {}, machine_counts: {}, bala_machine: {}, equity_summary: [],
    last_skip: "—", strategies: [], sol_price_usd: null, config_digest: "—",
  },
  tables: {
    candidates: [], would_pings: [], sent_pings: [], open_positions: [],
    closed_positions: [], skips: [], events: [], errors: [],
  },
  safety: {
    redaction_status: "—", redaction_unsafe_hits: null,
    redaction_positive_control_ok: null, redaction_files_scanned: 0,
    ledger_delta_total: null, ledger_lines: null, baseline_before: "—",
    baseline_after: "—", wallet_signing_or_trading: false,
    public_or_subscriber_routing: false, read_only: true,
    dashboard_discord_sends: "NOT SUPPORTED", wallet_surface: "NONE",
    old_ceremony_ledger: "NOT TOUCHED",
    notes: ["Mock fallback — start PHX2/dashboard/server.py for real artifacts."],
  },
};

function statusPillTone(status) {
  return { RUNNING: "ok", STOPPED: "info", STALE: "warn", UNKNOWN: "muted" }[status] || "muted";
}

function EmptyRow({ span, children }) {
  return (
    <tr>
      <td colSpan={span}>
        <div className="empty-state">{children}</div>
      </td>
    </tr>
  );
}

function num(v) {
  if (v == null) return "—";
  if (typeof v === "number") return v.toLocaleString();
  return String(v);
}

function capPair(v, cap) {
  return num(v) + (cap != null ? " / " + num(cap) : "");
}

function PaperPage() {
  const D = usePhxData("paper", MOCK_PAPER);
  const meta = usePhxMeta();
  const live = usePhxLive();

  const prod = D.system.producer;
  const pap = D.system.paper;
  const dis = D.discord;
  const dv = D.discovery;
  const cp = D.credit_panel || {};
  const tr = D.trading;
  const T = D.tables;
  const S = D.safety;

  const noSend = Object.entries(dv.no_send_reasons || {});
  const skips = Object.entries(tr.skip_reasons || {});
  const machine = Object.entries(tr.machine_counts || {});
  const watchByStatus = Object.entries(dv.watch_by_status || {});
  const rp = tr.risk_protection || {};
  const rb = rp.producer_by_label || {};

  return (
    <div className="live-page">
      {/* Header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Paper Trading / Live Pings</div>
          <h1 className="live-h1">
            Paper &amp; Pings
            <span className="live-pulse">
              <PulseDot /> {prod.status === "RUNNING" || pap.status === "RUNNING" ? "live artifacts" : "artifact snapshot"}
            </span>
          </h1>
        </div>
        <div className="live-head-meta">
          <span className="meta-chunk"><span className="meta-k">producer run</span><span className="meta-v">{prod.run_id}</span></span>
          <span className="meta-chunk"><span className="meta-k">paper run</span><span className="meta-v">{pap.run_id}</span></span>
          <span className="meta-chunk"><span className="meta-k">mode</span><span className="meta-v">{live ? "LIVE" : "MOCK"}</span></span>
        </div>
      </div>

      {/* Row 1 — System / Discord / Discovery */}
      <div className="live-row live-row-3">
        <Card
          eyebrow="01 · System"
          title="System Status"
          right={<Pill tone={statusPillTone(prod.status)}>{prod.status}</Pill>}
        >
          <div className="metric-grid">
            <MetricRow label="Producer" value={prod.status + (prod.stop_reason && prod.stop_reason !== "—" ? " · " + prod.stop_reason : "")} tone={prod.tone} />
            <MetricRow label="Producer Heartbeat" value={prod.heartbeat_age + " ago"} tone="info" />
            <MetricRow label="Producer Mode" value={prod.mode} tone="info" />
            <MetricRow label="Producer Tick" value={num(prod.tick)} tone="info" />
            <MetricRow label="Paper Engine" value={pap.status} tone={pap.tone} />
            <MetricRow label="Paper Heartbeat" value={pap.heartbeat_age + " ago"} tone="info" />
            <MetricRow label="Paper Uptime" value={pap.uptime || "—"} tone="info" />
            <MetricRow label="Snapshots Processed" value={num(pap.snapshots_processed)} tone="info" />
            <MetricRow label="Last Stop Reason" value={prod.stop_reason || "—"} tone={prod.stop_reason && prod.stop_reason !== "—" ? "warn" : "muted"} />
            <MetricRow label="Last Update (UTC)" value={String(prod.last_update_utc).replace("T", " ").replace("Z", "")} tone="muted" />
          </div>
        </Card>

        <Card
          eyebrow="02 · Private Discord"
          title="Private Discord Status"
          right={<Pill tone={dis.enabled_tone}>{dis.enabled === "YES" ? "ENABLED" : dis.enabled === "NO" ? "DISABLED" : "UNKNOWN"}</Pill>}
        >
          <div className="metric-grid">
            <MetricRow label="Private Discord Enabled" value={dis.enabled} tone={dis.enabled_tone} />
            <MetricRow label="Last Ping Result" value={dis.last_ping_result} tone={dis.last_ping_tone} />
            <MetricRow label="Run Outcome" value={dis.outcome} tone="info" />
            <MetricRow label="Private Pings Sent" value={num(dis.private_ping_count)} tone={dis.private_ping_count ? "ok" : "info"} />
            <MetricRow label="Would-ping Count" value={num(dis.would_ping_count)} tone="info" />
            <MetricRow label="Send Attempts / OK" value={num(dis.send_attempts) + " / " + num(dis.sent_ok_count)} tone="info" />
            <MetricRow label="Max Sends per Run" value={num(dis.max_sends_per_run)} tone="muted" />
            <MetricRow label="Last Would-Ping" value={dis.last_would_ping || "—"} tone="muted" />
            <MetricRow label="Last Sent Ping" value={dis.last_sent_ping || "—"} tone="muted" />
            <MetricRow label="Last No-Ping Reason" value={dis.last_no_ping_reason || "—"} tone={dis.last_no_ping_reason && dis.last_no_ping_reason !== "—" ? "warn" : "muted"} />
            <MetricRow label="Dedupe Suppressed" value={num(dis.dedupe_suppressed_total)} tone="info" />
            <MetricRow label="Dedupe Ledger Lines" value={num(dis.ledger_lines)} tone="muted" />
            <MetricRow label="Ledger Δ This Run" value={num(dis.ledger_delta_total)} tone={dis.ledger_delta_total ? "warn" : "ok"} />
          </div>
          <div className="dq-note">{dis.routing_note} · webhook value is never read or displayed.</div>
        </Card>

        <Card
          eyebrow="03 · Budget"
          title="Discovery / Credit Budget"
          right={<span className="meta-chunk"><span className="meta-k">ticks</span><span className="meta-v">{num(dv.ticks)}</span></span>}
        >
          <div className="delta-list">
            <div className="delta-row"><span className="delta-lbl">WS Notifications Seen</span><span className="delta-val delta-info">{capPair(dv.ws_notifications_seen, dv.ws_notifications_cap)}</span></div>
            <div className="delta-row"><span className="delta-lbl">Seed Windows</span><span className="delta-val delta-info">{capPair(dv.seed_windows, dv.seed_windows_cap)}</span></div>
            <div className="delta-row"><span className="delta-lbl">Candidates (budget)</span><span className="delta-val delta-ember">{capPair(dv.candidate_count, dv.candidate_cap)}</span></div>
            <div className="delta-row"><span className="delta-lbl">Watchlist Total</span><span className="delta-val delta-watching">{num(dv.watch_total)}</span></div>
            {watchByStatus.map(([k, v]) => (
              <div key={k} className="delta-row"><span className="delta-lbl">· {k}</span><span className="delta-val delta-muted">{num(v)}</span></div>
            ))}
            <div className="delta-row"><span className="delta-lbl">Market Requests (keyless/DEX)</span><span className="delta-val delta-info">{capPair(dv.market_requests, dv.market_requests_cap)}</span></div>
            <div className="delta-row"><span className="delta-lbl">· pairs / ohlcv / cache</span><span className="delta-val delta-muted">{num(dv.market_pairs_calls)} / {num(dv.market_ohlcv_calls)} / {num(dv.market_cache_hits)}</span></div>
            <div className="delta-row"><span className="delta-lbl">Market 429s</span><span className={"delta-val " + (dv.market_http_429 ? "delta-bad" : "delta-ok")}>{num(dv.market_http_429)}</span></div>
            <div className="delta-row"><span className="delta-lbl">getTransaction Fetches</span><span className="delta-val delta-info">{capPair(dv.gettransaction_fetches, dv.gettransaction_cap)}</span></div>
            <div className="delta-row"><span className="delta-lbl">Helius/RPC 429s</span><span className={"delta-val " + (dv.rpc_429_count ? "delta-bad" : "delta-ok")}>{capPair(dv.rpc_429_count, dv.rpc_429_cap)}</span></div>
            <div className="delta-row"><span className="delta-lbl">RPC Errors</span><span className={"delta-val " + (dv.rpc_errors_total ? "delta-warn" : "delta-ok")}>{num(dv.rpc_errors_total)}</span></div>
            <div className="delta-row"><span className="delta-lbl">Re-seeds</span><span className="delta-val delta-info">{num(dv.reseeds)}</span></div>
            {dv.non_pump_guard_dropped != null && (
              <div className="delta-row"><span className="delta-lbl">Non-pump Guard Drops (pre-watchlist)</span><span className="delta-val delta-muted">{num(dv.non_pump_guard_dropped)}</span></div>
            )}
            {dv.axiom_pass_total != null && (
              <div className="delta-row"><span className="delta-lbl">Axiom Gate (pass / fail)</span><span className="delta-val delta-info">{num(dv.axiom_pass_total)} / {num(dv.axiom_fail_total)}</span></div>
            )}
            <div className="delta-row"><span className="delta-lbl">Budget Stop Reason</span><span className={"delta-val " + (dv.budget_stop_reason ? "delta-warn" : "delta-ok")}>{dv.budget_stop_reason || "none"}</span></div>
            {noSend.map(([k, v]) => (
              <div key={k} className="delta-row"><span className="delta-lbl">no-send · {k}</span><span className="delta-val delta-warn">{num(v)}</span></div>
            ))}
            {dv.remaining && dv.remaining.ws_notifications != null && (
              <div className="delta-row"><span className="delta-lbl">Remaining · WS budget</span><span className="delta-val delta-ok">{num(dv.remaining.ws_notifications)}</span></div>
            )}
            {dv.remaining && dv.remaining.market_requests != null && (
              <div className="delta-row"><span className="delta-lbl">Remaining · market req</span><span className="delta-val delta-ok">{num(dv.remaining.market_requests)}</span></div>
            )}
            {dv.remaining && dv.remaining.sends != null && (
              <div className="delta-row"><span className="delta-lbl">Remaining · sends</span><span className="delta-val delta-ok">{num(dv.remaining.sends)}</span></div>
            )}
            {dv.remaining && dv.remaining.candidates != null && (
              <div className="delta-row"><span className="delta-lbl">Remaining · candidates</span><span className="delta-val delta-ok">{num(dv.remaining.candidates)}</span></div>
            )}
          </div>
        </Card>
      </div>

      {/* Row 1b — Helius Credit Panel (manual / operator-entered; never auto-read) */}
      <Card
        eyebrow="03b · Credits"
        title="Helius Credit Panel"
        right={<span className="meta-chunk"><span className="meta-k">entry</span><span className="meta-v">{cp.entry_provided ? "MANUAL" : "NOT SET"}</span></span>}
      >
        <div className="delta-list">
          <div className="delta-row"><span className="delta-lbl">Discovery Mode</span><span className="delta-val delta-info">{cp.discovery_mode || "—"}</span></div>
          <div className="delta-row"><span className="delta-lbl">Raw WS Msgs (NOT Helius credits)</span><span className="delta-val delta-muted">{num(cp.raw_ws_msg_count)}</span></div>
          <div className="delta-row"><span className="delta-lbl">Polling TX Fetched</span><span className="delta-val delta-info">{num(cp.polling_tx_count)}</span></div>
          <div className="delta-row"><span className="delta-lbl">getTransaction Fetches</span><span className="delta-val delta-info">{num(cp.gettransaction_fetches)}</span></div>
          <div className="delta-row"><span className="delta-lbl">Market HTTP Calls (keyless · not Helius)</span><span className="delta-val delta-info">{num(cp.market_http_calls)}</span></div>
          <div className="delta-row"><span className="delta-lbl">Private Pings Sent</span><span className="delta-val delta-ember">{num(cp.sent_pings)}</span></div>
          {cp.entry_provided ? (
            <React.Fragment>
              <div className="delta-row"><span className="delta-lbl">Credits Used (Δ before→after)</span><span className="delta-val delta-warn">{num(cp.credits_used)}</span></div>
              <div className="delta-row"><span className="delta-lbl">Credits / Hour</span><span className="delta-val delta-warn">{num(cp.credits_per_hour)}</span></div>
              <div className="delta-row"><span className="delta-lbl">Credits / Day (projected)</span><span className="delta-val delta-warn">{num(cp.credits_per_day)}</span></div>
              <div className="delta-row"><span className="delta-lbl">Credits / Ping</span><span className="delta-val delta-info">{num(cp.credits_per_ping)}</span></div>
              <div className="delta-row"><span className="delta-lbl">Days to 1M Exhaust</span><span className={"delta-val " + ((cp.days_to_exhaust != null && cp.days_to_exhaust < 7) ? "delta-bad" : "delta-info")}>{num(cp.days_to_exhaust)}</span></div>
              <div className="delta-row"><span className="delta-lbl">As Of (UTC)</span><span className="delta-val delta-muted">{cp.as_of_utc ? String(cp.as_of_utc).replace("T", " ").replace("Z", "") : "—"}</span></div>
            </React.Fragment>
          ) : (
            <div className="delta-row"><span className="delta-lbl">Credit burn estimate</span><span className="delta-val delta-muted">not set — {cp.entry_hint || "add helius_credits to config.json"}</span></div>
          )}
        </div>
        <div className="dq-note">{cp.source_note || "Helius credits are operator-entered; this dashboard never reads Helius, an API key, or any account."} · {cp.raw_ws_note}</div>
      </Card>

      {/* Risk protection — producer classifier + paper high-risk skips + observer bucket */}
      <Card
        eyebrow="03R · Risk"
        title="Scam / Bundle Risk Protection"
        right={<Pill tone={rb.HIGH ? "bad" : "ok"}>{rb.HIGH ? rb.HIGH + " HIGH" : "no HIGH"}</Pill>}
      >
        <div className="delta-list">
          <div className="delta-row"><span className="delta-lbl">Producer Risk H · M · L · ?</span><span className={"delta-val " + (rb.HIGH ? "delta-bad" : "delta-info")}>{num(rb.HIGH || 0)} · {num(rb.MEDIUM || 0)} · {num(rb.LOW || 0)} · {num(rb.UNKNOWN || 0)}</span></div>
          {/* Discord dispatch blocks (producer risk gate) — the private ping never left */}
          <div className="delta-row"><span className="delta-lbl">Discord Blocked · RISK_HIGH</span><span className={"delta-val " + (rp.discord_high_risk_block_count ? "delta-bad" : "delta-ok")}>{num(rp.discord_high_risk_block_count || 0)}</span></div>
          <div className="delta-row"><span className="delta-lbl">Legacy policy blocks · weak RISK_MEDIUM</span><span className={"delta-val " + (rp.discord_medium_structure_block_count ? "delta-warn" : "delta-ok")}>{num(rp.discord_medium_structure_block_count || 0)}</span></div>
          {Object.entries(rp.discord_high_risk_block_reasons || {}).map(([k, v]) => (
            <div key={"dh" + k} className="delta-row"><span className="delta-lbl">· blocked reason {k}</span><span className="delta-val delta-bad">{num(v)}</span></div>
          ))}
          {Object.entries(rp.discord_medium_block_reasons || {}).map(([k, v]) => (
            <div key={"dm" + k} className="delta-row"><span className="delta-lbl">· blocked reason {k}</span><span className="delta-val delta-warn">{num(v)}</span></div>
          ))}
          {(rp.discord_blocked_candidates || []).slice(-6).map((c, i) => (
            <div key={"dbc" + i} className="delta-row"><span className="delta-lbl">· blocked {c.token}</span><span className="delta-val delta-muted">{c.risk_label} · {c.mapped_reason}</span></div>
          ))}
          <div className="delta-row"><span className="delta-lbl">High-risk Paper Skips (total)</span><span className={"delta-val " + (rp.high_risk_skips_total ? "delta-warn" : "delta-ok")}>{num(rp.high_risk_skips_total)}</span></div>
          {Object.entries(rp.high_risk_skips_by_strategy || {}).map(([k, v]) => (
            <div key={"s" + k} className="delta-row"><span className="delta-lbl">· skips {k}</span><span className="delta-val delta-warn">{num(v)}</span></div>
          ))}
          {Object.entries(rp.high_risk_skip_reasons || {}).map(([k, v]) => (
            <div key={"r" + k} className="delta-row"><span className="delta-lbl">· reason {k}</span><span className="delta-val delta-muted">{num(v)}</span></div>
          ))}
          <div className="delta-row"><span className="delta-lbl">BALA Medium-risk Refusals</span><span className="delta-val delta-info">{num(rp.bala_risk_medium_skips)}</span></div>
          {rp.observer ? (
            <div className="delta-row"><span className="delta-lbl">Observer Bucket · {rp.observer.name}</span><span className="delta-val delta-ember">{num(rp.observer.high_risk_entries)} entries · open {num(rp.observer.open)} · closed {num(rp.observer.closed)} · PnL {rp.observer.total_pnl || "—"}</span></div>
          ) : (
            <div className="delta-row"><span className="delta-lbl">Observer Bucket</span><span className="delta-val delta-muted">not configured this run</span></div>
          )}
          <div className="delta-row"><span className="delta-lbl">Holder / Bundle Scan</span><span className="delta-val delta-muted">{rp.holder_scan_enabled ? "ENABLED" : "none (free tier — UNKNOWN by design)"}</span></div>
        </div>
        <div className="dq-note">{rp.discord_vs_paper_note || "'Discord blocked' = the risk gate stopped the private ping before reserve/send; 'Paper skipped' = paper strategies declined to trade it (the observer still tracks it)."}</div>
        <div className="dq-note">{rp.risk_note || "cheap free-tier heuristic; holder/bundler data UNKNOWN by design"} · {rp.clean_pnl_note || "strategy PnL excludes high-risk skips; the observer bucket is the only strategy trading RISK_HIGH"}</div>
      </Card>

      {/* Row 2 — Paper trading status */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="04 · Paper"
          title="Paper Trading Status"
          right={<Pill tone={statusPillTone(pap.status)}>{pap.status}</Pill>}
        >
          <div className="metric-grid">
            <MetricRow label="Open Positions" value={num(tr.open_positions)} tone="info" />
            <MetricRow label="Closed Positions" value={num(tr.closed_positions)} tone="info" />
            <MetricRow label="Realized PnL" value={tr.realized_pnl} tone={(tr.realized_raw || 0) < 0 ? "warn" : "ok"} />
            <MetricRow label="Unrealized PnL" value={tr.unrealized_pnl} tone={(tr.unrealized_raw || 0) < 0 ? "warn" : "ok"} />
            <MetricRow label="Total PnL" value={tr.total_pnl || "—"} tone="info" />
            <MetricRow label="Win Rate" value={tr.win_rate || "—"} tone="info" />
            <MetricRow label="Best Trade" value={tr.best_trade || "—"} tone="muted" />
            <MetricRow label="Worst Trade" value={tr.worst_trade || "—"} tone="muted" />
            <MetricRow label="BALA_PLAN State" value={Object.entries(tr.bala_machine || {}).map(([k, v]) => k + " " + v).join(" · ") || "—"} tone="watching" />
            <MetricRow label="Latest Skip" value={tr.last_skip} tone={tr.last_skip && tr.last_skip !== "—" ? "warn" : "muted"} />
            <MetricRow label="Paper Last Error" value={pap.last_error} tone={pap.last_error && pap.last_error !== "—" ? "warn" : "muted"} />
            <MetricRow label="SOL Price (USD)" value={tr.sol_price_usd != null ? String(tr.sol_price_usd) : "—"} tone="muted" />
            <MetricRow label="Config Digest" value={tr.config_digest || "—"} tone="muted" />
          </div>
          {(skips.length > 0 || machine.length > 0) && (
            <div className="delta-list" style={{ marginTop: 10 }}>
              {skips.map(([k, v]) => (
                <div key={k} className="delta-row"><span className="delta-lbl">skip · {k}</span><span className="delta-val delta-warn">{num(v)}</span></div>
              ))}
              {machine.map(([k, v]) => (
                <div key={k} className="delta-row"><span className="delta-lbl">machine · {k}</span><span className="delta-val delta-muted">{num(v)}</span></div>
              ))}
            </div>
          )}
        </Card>

        <Card
          eyebrow="05 · Strategies"
          title="Strategy Accounts · each starts at $1,000"
          right={<span className="meta-chunk"><span className="meta-k">strategies</span><span className="meta-v">{T && tr.strategies ? tr.strategies.length : 0}</span></span>}
        >
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Strategy</th>
                  <th className="num">Starting Equity</th>
                  <th className="num">Current Equity</th>
                  <th className="num">Realized PnL</th>
                  <th className="num">Unrealized PnL</th>
                  <th className="num">Total PnL</th>
                  <th className="num">Return %</th>
                  <th className="num">Win Rate</th>
                  <th className="num">Open</th>
                  <th className="num">Closed</th>
                  <th className="num">Skipped</th>
                  <th className="num">HR Skips</th>
                  <th className="num">Rugged</th>
                  <th className="num">Lost</th>
                  <th className="num">Max DD</th>
                  <th>Best / Worst</th>
                </tr>
              </thead>
              <tbody>
                {(!tr.strategies || tr.strategies.length === 0) && <EmptyRow span={17}>No strategy data yet</EmptyRow>}
                {(tr.strategies || []).map((s) => (
                  <tr key={s.name}>
                    <td className="num mono mute">#{num(s.rank)}</td>
                    <td><span className="tok-sym">{s.name}</span></td>
                    <td className="num mono">{s.starting || "$1,000.00"}</td>
                    <td className="num mono">{s.equity}</td>
                    <td className="num mono">{s.realized}</td>
                    <td className="num mono">{s.unrealized}</td>
                    <td className="num mono">{s.total || s.pnl_usd}</td>
                    <td className="num mono">{s.return_pct || s.pnl_pct}</td>
                    <td className="num mono">{s.win_rate}</td>
                    <td className="num mono">{num(s.open)}</td>
                    <td className="num mono">{num(s.closed)}</td>
                    <td className={"num mono " + (s.skipped ? "warn" : "mute")}>{num(s.skipped)}</td>
                    <td className={"num mono " + (s.high_risk_skips ? "warn" : "mute")}>{num(s.high_risk_skips)}</td>
                    <td className={"num mono " + (s.rugged ? "warn" : "mute")}>{num(s.rugged)}</td>
                    <td className={"num mono " + (s.data_lost ? "warn" : "mute")}>{num(s.data_lost)}</td>
                    <td className="num mono">{s.max_dd}</td>
                    <td className="mono mute">{s.best} / {s.worst}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {tr.equity_summary && tr.equity_summary.length > 0 && (
            <div className="dq-note" style={{ marginTop: 8 }}>
              equity curve (latest point per strategy): {tr.equity_summary.map((e) => `${e.strategy} ${e.equity} (${e.points} pts, ${e.as_of})`).join(" · ")}
            </div>
          )}
        </Card>
      </div>

      {/* Row 3 — Watchlist + ping tables */}
      <Card
        eyebrow="06 · Watchlist"
        title="Recent Candidates (Producer Watchlist)"
        right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{T.candidates.length}</span></span>}
      >
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Token</th>
                <th>Mint</th>
                <th>Status</th>
                <th className="num">Market Cap</th>
                <th className="num">Liquidity</th>
                <th>Blocker</th>
                <th className="num">Rechecks</th>
                <th className="num">Migration Age</th>
                <th className="num">In Queue</th>
                <th className="num">Updated</th>
              </tr>
            </thead>
            <tbody>
              {T.candidates.length === 0 && <EmptyRow span={10}>No candidates yet — watchlist artifact empty or missing</EmptyRow>}
              {T.candidates.map((c) => (
                <tr key={c.id}>
                  <td><span className="tok-sym">{c.token}</span></td>
                  <td className="mono mute">{c.tokenSub}<CopyCA value={c.mint} /></td>
                  <td><Pill tone={c.stage === "WATCHING" ? "watching" : c.stage === "DEAD" ? "bad" : "warn"} dim>{c.filters}</Pill></td>
                  <td className="num mono">{c.mcap}</td>
                  <td className="num mono">{c.liq}</td>
                  <td className="reason">{c.blocker}</td>
                  <td className="num mono mute">{num(c.recheckCount)}</td>
                  <td className="num mono mute">{c.migrationAge}</td>
                  <td className="num mono mute">{c.timeInQueue}</td>
                  <td className="num mono mute">{c.updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="live-row cand-bottom">
        <Card
          eyebrow="07 · Would-Ping"
          title="Recent Would-Ping Events"
          right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{T.would_pings.length}</span></span>}
        >
          {T.would_pings.length === 0 ? (
            <div className="empty-state">No would-ping records this run</div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Token</th><th>Reason</th><th className="num">When</th></tr></thead>
                <tbody>
                  {T.would_pings.map((r, i) => (
                    <tr key={i}>
                      <td className="mono">{r.token}<CopyCA value={r.mint} /></td>
                      <td><span className="reason-chip mono">{r.reason}</span></td>
                      <td className="num mono mute">{r.at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          eyebrow="08 · Sent"
          title="Recent Private Pings Sent"
          right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{T.sent_pings.length}</span></span>}
        >
          {T.sent_pings.length === 0 ? (
            <div className="empty-state">No private pings sent this run</div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Token</th><th>Result</th><th className="num">When</th></tr></thead>
                <tbody>
                  {T.sent_pings.map((r, i) => (
                    <tr key={i}>
                      <td className="mono">{r.token}<CopyCA value={r.mint} /></td>
                      <td><Pill tone="called">{r.result}</Pill></td>
                      <td className="num mono mute">{r.at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Row 4 — positions */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="09 · Entries"
          title="Open Entries"
          right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{T.open_positions.length}</span></span>}
        >
          {T.open_positions.length === 0 ? (
            <div className="empty-state">No paper entries yet</div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Token</th>
                    <th className="num">Entered</th>
                    <th className="num">Entry Px</th>
                    <th className="num">Entry MCap</th>
                    <th className="num">Tokens</th>
                    <th className="num">Cost Basis</th>
                    <th className="num">Current Value</th>
                    <th className="num">Unrealized</th>
                    <th>State / Leg</th>
                  </tr>
                </thead>
                <tbody>
                  {T.open_positions.map((p, i) => (
                    <tr key={i}>
                      <td><span className="tok-sym">{p.strategy}</span></td>
                      <td className="mono">{p.token}<CopyCA value={p.mint} /></td>
                      <td className="num mono mute">{p.opened} <span className="mute">· {p.opened_abs}</span></td>
                      <td className="num mono">{p.entry}</td>
                      <td className="num mono">{p.entry_mcap}</td>
                      <td className="num mono">{p.tokens}</td>
                      <td className="num mono">{p.cost}</td>
                      <td className="num mono">{p.value}</td>
                      <td className="num mono">{p.unrealized} ({p.unrealized_pct})</td>
                      <td><Pill tone="watching" dim>{p.state}</Pill></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          eyebrow="10 · Exits"
          title="Closed Exits"
          right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{T.closed_positions.length}</span></span>}
        >
          {T.closed_positions.length === 0 ? (
            <div className="empty-state">No paper exits yet</div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead>
                  <tr>
                    <th>Strategy</th>
                    <th>Token</th>
                    <th className="num">Entered</th>
                    <th className="num">Exited</th>
                    <th className="num">Entry Px</th>
                    <th className="num">Exit Px</th>
                    <th className="num">Tokens</th>
                    <th className="num">Realized PnL</th>
                    <th className="num">Return %</th>
                    <th className="num">Hold</th>
                    <th>Exit Reason</th>
                  </tr>
                </thead>
                <tbody>
                  {T.closed_positions.map((p, i) => (
                    <tr key={i}>
                      <td><span className="tok-sym">{p.strategy}</span></td>
                      <td className="mono">{p.token}<CopyCA value={p.mint} /></td>
                      <td className="num mono mute">{p.entered}</td>
                      <td className="num mono mute">{p.closed} <span className="mute">· {p.closed_abs}</span></td>
                      <td className="num mono">{p.entry_price}</td>
                      <td className="num mono">{p.exit_price}</td>
                      <td className="num mono">{p.tokens}</td>
                      <td className="num mono">{p.pnl_usd}</td>
                      <td className="num mono">{p.pnl_pct}</td>
                      <td className="num mono mute">{p.hold}</td>
                      <td><span className="reason-chip mono">{p.reason}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Row 5 — events / skips / errors */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="11 · Events"
          title="Recent Paper Events & Skips"
          right={<span className="meta-chunk"><span className="meta-k">events</span><span className="meta-v">{T.events.length}</span></span>}
        >
          {T.skips.length > 0 && (
            <div className="delta-list" style={{ marginBottom: 10 }}>
              {T.skips.map((s, i) => (
                <div key={i} className="delta-row">
                  <span className="delta-lbl">{s.strategy} · {s.token}<CopyCA value={s.mint} /></span>
                  <span className={"delta-val " + (s.high_risk_skip ? "delta-bad" : "delta-warn")}>{s.reason}{s.risk && s.risk !== "?" ? " · risk " + s.risk : ""}</span>
                </div>
              ))}
            </div>
          )}
          {T.events.length === 0 ? (
            <div className="empty-state">No paper events yet</div>
          ) : (
            <div className="dec-strip" style={{ gridAutoFlow: "row" }}>
              {T.events.slice(0, 9).map((e, i) => (
                <div key={i} className="dec-card dec-watching">
                  <div className="dec-top">
                    <span className="dec-t">{e.t}</span>
                    <span className="dec-type dec-type-watching">{e.event}</span>
                  </div>
                  {e.token && (
                    <div className="dec-tok">{e.token}<CopyCA value={e.mint} /></div>
                  )}
                  <div className="dec-reason">{e.reason ? e.reason + " · " : ""}{e.detail}</div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          eyebrow="12 · Errors"
          title="Recent Errors"
          right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{T.errors.length}</span></span>}
        >
          {T.errors.length === 0 ? (
            <div className="empty-state">No errors recorded</div>
          ) : (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Source</th><th>Kind</th><th>Detail</th><th>File</th></tr></thead>
                <tbody>
                  {T.errors.map((e, i) => (
                    <tr key={i}>
                      <td><Pill tone="warn" dim>{e.source}</Pill></td>
                      <td className="mono">{e.kind}</td>
                      <td className="reason">{e.detail}</td>
                      <td className="mono mute">{e.file}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {/* Row 6 — Safety / redaction */}
      <Card
        eyebrow="13 · Safety"
        title="Safety / Redaction"
        right={<Pill tone={S.redaction_status === "REDACTED" ? "ok" : "warn"}>{S.redaction_status === "REDACTED" ? "REDACTED" : String(S.redaction_status)}</Pill>}
      >
        <div className="live-row live-row-3">
          <div className="metric-grid">
            <MetricRow label="Redaction Scan" value={String(S.redaction_status)} tone={S.redaction_status === "REDACTED" ? "ok" : "warn"} />
            <MetricRow label="Unsafe Hits" value={num(S.redaction_unsafe_hits)} tone={S.redaction_unsafe_hits ? "bad" : "ok"} />
            <MetricRow label="Positive Control" value={S.redaction_positive_control_ok === true ? "OK" : S.redaction_positive_control_ok === false ? "FAILED" : "—"} tone={S.redaction_positive_control_ok ? "ok" : "warn"} />
            <MetricRow label="Files Scanned" value={num(S.redaction_files_scanned)} tone="info" />
          </div>
          <div className="metric-grid">
            <MetricRow label="Ledger Δ This Run" value={num(S.ledger_delta_total)} tone={S.ledger_delta_total ? "warn" : "ok"} />
            <MetricRow label="Ledger Lines" value={num(S.ledger_lines)} tone="muted" />
            <MetricRow label="Baseline Before" value={S.baseline_before} tone="muted" />
            <MetricRow label="Baseline After" value={S.baseline_after} tone="muted" />
          </div>
          <div className="metric-grid">
            <MetricRow label="Wallet / Signing / Trading" value={S.wallet_signing_or_trading ? "TRUE (!)" : "NONE"} tone={S.wallet_signing_or_trading ? "bad" : "ok"} />
            <MetricRow label="Public / Subscriber Routing" value={S.public_or_subscriber_routing ? "TRUE (!)" : "OFF (private only)"} tone={S.public_or_subscriber_routing ? "bad" : "ok"} />
            <MetricRow label="Dashboard Mode" value="READ-ONLY" tone="ok" />
            <MetricRow label="Dashboard Discord Sends" value={S.dashboard_discord_sends || "NOT SUPPORTED"} tone="ok" />
            <MetricRow label="Old Ceremony Ledger" value={S.old_ceremony_ledger || "NOT TOUCHED"} tone="ok" />
            <MetricRow label="Secrets Displayed" value="NEVER" tone="ok" />
          </div>
        </div>
        {S.notes && S.notes.length > 0 && (
          <div className="dq-note">
            {S.notes.map((n, i) => (<div key={i}>· {n}</div>))}
          </div>
        )}
        {meta && (
          <div className="dq-note" style={{ marginTop: 8 }}>
            <div>· producer artifacts: <span className="mono">{meta.producer_dir}</span></div>
            <div>· paper artifacts: <span className="mono">{meta.paper_dir}</span></div>
            <div>· bundle generated: <span className="mono">{meta.generated_at_utc}</span>{meta.errors && meta.errors.length ? " · adapter errors: " + meta.errors.join("; ") : " · no adapter errors"}</div>
          </div>
        )}
      </Card>

      <div className="live-foot">
        <span className="foot-mute">{live ? "artifact-backed · read-only · no dispatch from dashboard" : "MOCK fallback · start server.py for real artifacts"}</span>
        <span className="foot-mute foot-pulse"><PulseDot /> paper &amp; pings</span>
      </div>
    </div>
  );
}

window.PaperPage = PaperPage;
