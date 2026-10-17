// Phoenix — Runs page (operational audit / artifact browser)
// Design-mock kept as fallback; real producer/paper run metadata from
// usePhxData("runs", …). Read-only.

const MOCK_RUNS = {
  stages: [
    { id: "S21", label: "Stage 21", title: "Discord smoke", status: "closed" },
    { id: "S22", label: "Stage 22", title: "Live ingest + dedupe", status: "closed" },
    { id: "S23", label: "Stage 23", title: "Decision layer", status: "closed" },
    { id: "S24", label: "Stage 24", title: "Filter calibration", status: "closed" },
    { id: "S25", label: "Stage 25", title: "Outcome measurement", status: "closed" },
    { id: "S26", label: "Stage 26", title: "Policy + closure audit", status: "review" },
    { id: "S27", label: "Stage 27", title: "Live promotion", status: "next" },
  ],
  runs: [
    {
      id: "stage22_live_smoke_001", stage: "Stage 22", runType: "LIVE_INGEST",
      started: "2m", startedAbs: "14:22:51", duration: "1.4s", status: "PASS",
      inputs: "Helius gRPC stream · 1 tx", outputs: "raw_capture + dedupe_ledger",
      artifactsCount: 2, rows: "1 event", warnings: 0, errors: 0, tests: 12,
      manifestHash: "a47f9c2e", note: "Run passed. Raw capture and dedupe artifacts written. No malformed events.",
    },
    {
      id: "stage25_measure_014", stage: "Stage 25", runType: "OUTCOME_BUILD",
      started: "14m", startedAbs: "14:11:08", duration: "42.6s", status: "PASS",
      inputs: "801 decisions · 4h window", outputs: "outcome_ledger.parquet",
      artifactsCount: 3, rows: "801 rows", warnings: 0, errors: 0, tests: 28,
      manifestHash: "b9e34112", note: "ATH and migration measurement complete. All decisions resolved within the window.",
    },
    {
      id: "stage26_policy_003", stage: "Stage 26", runType: "CALIBRATION_BUILD",
      started: "32m", startedAbs: "13:50:44", duration: "1m 14s", status: "WARN",
      inputs: "646 candidate cohort", outputs: "policy_candidates + review_packet",
      artifactsCount: 4, rows: "646 rows", warnings: 2, errors: 0, tests: 41,
      warningTypes: ["Low Sample Size", "Partial Output"],
      manifestHash: "d12fac88", note: "Run completed with warning: low sample size in candidate policy cohort. Review packet generated for manual inspection.",
    },
    {
      id: "stage21_smoke_002", stage: "Stage 21", runType: "SMOKE_TEST",
      started: "1h 04m", startedAbs: "13:19:12", duration: "0.8s", status: "PASS",
      inputs: "1 ping payload", outputs: "discord_smoke_ack",
      artifactsCount: 1, rows: "1 ping", warnings: 0, errors: 0, tests: 6,
      manifestHash: "37a0c5e1", note: "Private Discord smoke ping accepted (acknowledged).",
    },
    {
      id: "replay_ath_gap_007", stage: "Stage 25", runType: "REPLAY",
      started: "1h 38m", startedAbs: "12:45:30", duration: "2m 06s", status: "PARTIAL",
      inputs: "44 tokens · gap window", outputs: "replay_measurement.parquet",
      artifactsCount: 2, rows: "44 tokens", warnings: 4, errors: 0, tests: 18,
      warningTypes: ["Missing ATH", "Missing ATH", "Missing ATH", "Missing ATH"],
      manifestHash: "5ce81d44", note: "Replay partial: ATH unknown for 4 tokens. Remaining 40 measured cleanly.",
    },
    {
      id: "stage26_closure_audit_mock", stage: "Stage 26", runType: "CLOSURE_AUDIT",
      started: "2h 12m", startedAbs: "12:11:08", duration: "3.4s", status: "PASS",
      inputs: "80 audit assertions", outputs: "closure_audit_report.json",
      artifactsCount: 1, rows: "80 tests", warnings: 0, errors: 0, tests: 80,
      manifestHash: "f2901e7c", note: "Closure audit clean. All 80 assertions passed.",
    },
    {
      id: "stage22_live_smoke_002", stage: "Stage 22", runType: "LIVE_INGEST",
      started: "2h 38m", startedAbs: "11:44:52", duration: "1.1s", status: "PASS",
      inputs: "Helius gRPC stream · 1 tx", outputs: "raw_capture + dedupe_ledger",
      artifactsCount: 2, rows: "1 event", warnings: 0, errors: 0, tests: 12,
      manifestHash: "0e3a8b71", note: "Standard ingest tick.",
    },
    {
      id: "stage23_decision_018", stage: "Stage 23", runType: "STAGE_ARTIFACT",
      started: "3h 04m", startedAbs: "11:18:14", duration: "14.2s", status: "PASS",
      inputs: "1,284 events · 6h window", outputs: "decision_ledger.parquet",
      artifactsCount: 3, rows: "1,284 rows", warnings: 0, errors: 0, tests: 34,
      manifestHash: "8d7c2efa", note: "Decision artifact written. All filter contexts evaluated cleanly.",
    },
    {
      id: "stage26_review_packet_009", stage: "Stage 26", runType: "REVIEW_PACKET_BUILD",
      started: "3h 41m", startedAbs: "10:40:30", duration: "8.7s", status: "PASS",
      inputs: "126 candidate evaluations", outputs: "review_packet_2026-05-21.zip",
      artifactsCount: 1, rows: "126 rows", warnings: 0, errors: 0, tests: 9,
      manifestHash: "9b41c0a3", note: "Review packet built for human inspection.",
    },
    {
      id: "stage24_filter_calib_022", stage: "Stage 24", runType: "CALIBRATION_BUILD",
      started: "4h 10m", startedAbs: "10:12:48", duration: "32.1s", status: "WARN",
      inputs: "412 labeled cohort", outputs: "filter_calibration.json",
      artifactsCount: 2, rows: "412 rows", warnings: 1, errors: 0, tests: 27,
      warningTypes: ["Low Sample Size"],
      manifestHash: "c70a5e69", note: "Filter calibration written. Bundle-risk cohort below recommended sample threshold.",
    },
    {
      id: "stage22_live_smoke_003", stage: "Stage 22", runType: "LIVE_INGEST",
      started: "5h 22m", startedAbs: "08:50:48", duration: "0.9s", status: "WARN",
      inputs: "Helius gRPC stream · 1 tx", outputs: "raw_capture",
      artifactsCount: 1, rows: "1 event", warnings: 1, errors: 0, tests: 12,
      warningTypes: ["Malformed Event"],
      manifestHash: "21e84f0c", note: "Single malformed event observed (1/1284 = 0.08%). Below threshold.",
    },
    {
      id: "replay_outcome_full_011", stage: "Stage 25", runType: "REPLAY",
      started: "8h 14m", startedAbs: "06:08:14", duration: "4m 22s", status: "PASS",
      inputs: "all 21 outcomes", outputs: "outcome_replay.parquet",
      artifactsCount: 3, rows: "21 rows", warnings: 0, errors: 0, tests: 21,
      manifestHash: "ae29d1f5", note: "Full outcome replay verified — all rows reproduced byte-for-byte.",
    },
    {
      id: "stage25_measure_013", stage: "Stage 25", runType: "OUTCOME_BUILD",
      started: "12h", startedAbs: "02:22:18", duration: "44.1s", status: "FAIL",
      inputs: "788 decisions · 4h window", outputs: "—",
      artifactsCount: 0, rows: "—", warnings: 1, errors: 1, tests: 27,
      warningTypes: ["Provider Failure"],
      manifestHash: "—", note: "Helius provider returned 503 mid-run. Re-run scheduled as stage25_measure_014. No artifact written.",
    },
    {
      id: "stage22_dedupe_smoke_004", stage: "Stage 22", runType: "SMOKE_TEST",
      started: "1d 02h", startedAbs: "12:00 yesterday", duration: "1.7s", status: "PASS",
      inputs: "12 dedupe assertions", outputs: "dedupe_smoke_report",
      artifactsCount: 1, rows: "12 tests", warnings: 0, errors: 0, tests: 12,
      manifestHash: "44b9e2c0", note: "Dedupe ledger consistency verified.",
    },
    {
      id: "stage25_outcome_partial_005", stage: "Stage 25", runType: "OUTCOME_BUILD",
      started: "1d 09h", startedAbs: "05:14 yesterday", duration: "1m 38s", status: "PARTIAL",
      inputs: "612 decisions", outputs: "outcome_partial.parquet",
      artifactsCount: 2, rows: "598 rows", warnings: 3, errors: 0, tests: 28,
      warningTypes: ["Price Stale", "Missing ATH", "Dedupe Duplicate"],
      manifestHash: "1f7be4ad", note: "Partial run: 14 decisions skipped due to stale/missing inputs. Resolvable on re-run.",
    },
    {
      id: "stage26_closure_001", stage: "Stage 26", runType: "CLOSURE_AUDIT",
      started: "2d 04h", startedAbs: "10:00 -2d", duration: "2.9s", status: "WARN",
      inputs: "80 assertions", outputs: "closure_audit_v1.json",
      artifactsCount: 1, rows: "80 tests", warnings: 1, errors: 0, tests: 80,
      warningTypes: ["Test Warning"],
      manifestHash: "06fa9c2d", note: "78/80 passed, 2 soft warnings on USDC lane assertions. Acceptable for Stage 26 review.",
    },
  ],
};

// Build artifacts from runs. Real runs carry an explicit artifactsList
// (actual files on disk); the design mock derives names from run type.
function buildRunArtifacts(runs) {
  const out = [];
  runs.forEach((r) => {
    if (r.artifactsList) {
      r.artifactsList.forEach((a) => out.push(a));
      return;
    }
    if (r.artifactsCount === 0) return;
    const labels = {
      LIVE_INGEST: ["raw_capture.parquet", "dedupe_ledger.json"],
      SMOKE_TEST: ["smoke_report.json"],
      OUTCOME_BUILD: ["outcome_ledger.parquet", "outcome_index.json", "ath_map.parquet"],
      REPLAY: ["replay_measurement.parquet", "replay_index.json", "replay_manifest.json"],
      CLOSURE_AUDIT: ["closure_audit.json"],
      STAGE_ARTIFACT: ["decision_ledger.parquet", "filter_index.json", "stage_manifest.json"],
      CALIBRATION_BUILD: ["policy_candidates.json", "review_packet.zip", "calibration_summary.json", "filter_thresholds.json"],
      REVIEW_PACKET_BUILD: ["review_packet.zip"],
    };
    const set = (labels[r.runType] || ["artifact.json"]).slice(0, r.artifactsCount);
    set.forEach((name, i) => {
      const artStatus = r.status === "FAIL" ? "FAIL"
        : (r.status === "WARN" && i === 0) ? "WARN"
        : "OK";
      out.push({
        id: r.id + "::" + name,
        name,
        type: artTypeFromName(name),
        stage: r.stage,
        runId: r.id,
        rows: r.rows,
        created: r.started + " ago",
        hash: r.manifestHash === "—" ? "—" : (r.manifestHash + (i ? "·" + (i+1).toString(36) : "")),
        status: artStatus,
        notes: r.warningTypes && r.warningTypes[i] ? r.warningTypes[i] : (artStatus === "OK" ? "—" : "see run notes"),
      });
    });
  });
  return out;
}

function artTypeFromName(name) {
  if (name.includes("raw_capture")) return "Raw Capture";
  if (name.includes("dedupe")) return "Dedupe Ledger";
  if (name.includes("decision")) return "Decision Artifact";
  if (name.includes("outcome") || name.includes("ath_map")) return "Outcome Artifact";
  if (name.includes("calibration") || name.includes("filter_thresholds") || name.includes("policy_candidates")) return "Calibration Artifact";
  if (name.includes("review_packet")) return "Review Packet";
  if (name.includes("closure_audit")) return "Closure Audit";
  if (name.includes("manifest")) return "Manifest";
  if (name.includes("smoke")) return "Operator Runbook";
  return "Manifest";
}

// ─── Tones ───────────────────────────────────────────────────────────
const runStatusTone = {
  PASS: "ok",
  WARN: "warn",
  FAIL: "bad",
  RUNNING: "ember",
  CANCELED: "muted",
  PARTIAL: "ember",
};
const runTypeTone = {
  LIVE_INGEST: "ok",
  REPLAY: "watching",
  STAGE_ARTIFACT: "ember",
  CLOSURE_AUDIT: "ember",
  SMOKE_TEST: "watching",
  CALIBRATION_BUILD: "watching",
  OUTCOME_BUILD: "ok",
  REVIEW_PACKET_BUILD: "ember",
};

function RunStatusPill({ value }) {
  return <span className={"pill pill-" + (runStatusTone[value] || "muted")}>{value}</span>;
}
function RunTypePill({ value }) {
  return <span className={"pill pill-" + (runTypeTone[value] || "muted") + " pill-dim"}>{value}</span>;
}

function Hash({ value }) {
  if (!value || value === "—") return <span className="hash hash-empty">—</span>;
  return <span className="hash" title={value}>#{value}</span>;
}

// ─── Summary ─────────────────────────────────────────────────────────
function buildRunSummary(runs, artifacts) {
  const isLive = (r) => /LIVE|PRIVATE|PRODUCER|PAPER/i.test(r.runType || "");
  return [
    { label: "Total Runs", value: runs.length, tone: "info" },
    { label: "Live Runs", value: runs.filter((r) => isLive(r) || r.runType === "LIVE_INGEST").length, tone: "ok" },
    { label: "Replay Runs", value: runs.filter((r) => r.runType === "REPLAY").length, tone: "watching" },
    { label: "Stage Runs", value: runs.filter((r) => ["STAGE_ARTIFACT","CALIBRATION_BUILD","OUTCOME_BUILD","CLOSURE_AUDIT","REVIEW_PACKET_BUILD"].includes(r.runType)).length, tone: "ember" },
    { label: "Passed", value: runs.filter((r) => r.status === "PASS").length, tone: "ok" },
    { label: "Warnings", value: runs.filter((r) => r.status === "WARN" || r.status === "PARTIAL").length, tone: "warn" },
    { label: "Failed", value: runs.filter((r) => r.status === "FAIL").length, tone: "bad" },
    { label: "Latest Run", value: runs.length ? runs[0].started : "—", tone: "info" },
    { label: "Artifacts Written", value: artifacts.length, tone: "ember" },
  ];
}

// ─── Warnings grouping (generic: groups by warning label) ────────────
function buildWarningGroups(runs) {
  const g = {};
  runs.forEach((r) => {
    (r.warningTypes || []).forEach((w) => {
      if (!g[w]) g[w] = [];
      g[w].push(r);
    });
  });
  return g;
}

// ─── Drawer ──────────────────────────────────────────────────────────
function RunDrawer({ run, onClose, onOpenArtifact, allArtifacts }) {
  if (!run) return null;
  const artifacts = (allArtifacts || []).filter((a) => a.runId === run.id);
  return (
    <>
      <div className="cd-scrim" onClick={onClose} />
      <aside className="cd-drawer">
        <div className="cd-hd">
          <div>
            <div className="cd-eyebrow">Run Detail</div>
            <div className="cd-title">
              <span className="cd-sym mono" style={{ fontSize: 16 }}>{run.id}</span>
            </div>
            <div className="cd-addr mono">{run.stage} · {run.runType}</div>
          </div>
          <button className="cd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="cd-stage-banner">
          <RunStatusPill value={run.status} />
          <RunTypePill value={run.runType} />
          <span className="cd-banner-update meta-chunk">
            <span className="meta-k">started</span>
            <span className="meta-v">{run.startedAbs} · {run.started} ago</span>
          </span>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Run Context</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Stage</span><b>{run.stage}</b></div>
            <div className="cd-kv"><span>Run type</span><b className="mono">{run.runType}</b></div>
            <div className="cd-kv"><span>Duration</span><b className="mono">{run.duration}</b></div>
            <div className="cd-kv"><span>Status</span><b><RunStatusPill value={run.status} /></b></div>
            <div className="cd-kv"><span>Tests</span><b className="mono">{run.tests}</b></div>
            <div className="cd-kv"><span>Warnings</span><b className={run.warnings ? "warn mono" : "ok mono"}>{run.warnings}</b></div>
            <div className="cd-kv"><span>Errors</span><b className={run.errors ? "warn mono" : "ok mono"}>{run.errors}</b></div>
            <div className="cd-kv"><span>Manifest hash</span><b><Hash value={run.manifestHash} /></b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Inputs / Outputs</div>
          <div className="io-grid">
            <div className="io-cell">
              <div className="io-lbl">Inputs</div>
              <div className="io-val mono">{run.inputs}</div>
            </div>
            <div className="io-cell">
              <div className="io-lbl">Outputs</div>
              <div className="io-val mono">{run.outputs}</div>
            </div>
            <div className="io-cell">
              <div className="io-lbl">Rows / Events</div>
              <div className="io-val mono">{run.rows}</div>
            </div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Artifacts ({artifacts.length})</div>
          {artifacts.length === 0 ? (
            <p className="cd-note">No artifacts written for this run.</p>
          ) : (
            <div className="art-list">
              {artifacts.map((a) => (
                <div key={a.id} className="art-row" onClick={() => onOpenArtifact && onOpenArtifact(a)}>
                  <div className="art-row-l">
                    <div className="art-name mono">{a.name}</div>
                    <div className="art-meta mono mute">{a.type} · {a.rows}</div>
                  </div>
                  <div className="art-row-r">
                    <Hash value={a.hash} />
                    <span className={"pill pill-" + (a.status === "OK" ? "ok" : a.status === "WARN" ? "warn" : "bad") + " pill-dim"}>{a.status}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {run.warningTypes && run.warningTypes.length > 0 && (
          <div className="cd-section">
            <div className="cd-section-hd">Warnings ({run.warningTypes.length})</div>
            <div className="warn-tags">
              {run.warningTypes.map((w, i) => (<span key={i} className="warn-tag">{w}</span>))}
            </div>
          </div>
        )}

        <div className="cd-section">
          <div className="cd-section-hd">Operator Note</div>
          <p className="cd-note">{run.note}</p>
        </div>

        <div className="cd-foot">
          <span className="foot-mute">read-only · run is immutable · artifacts are content-addressed</span>
        </div>
      </aside>
    </>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function RunsPage() {
  const RunData = usePhxData("runs", MOCK_RUNS);
  const live = usePhxLive();
  const [selected, setSelected] = React.useState(null);
  const [statusFilter, setStatusFilter] = React.useState("ALL");
  const [typeFilter, setTypeFilter] = React.useState("ALL");
  const [stageFilter, setStageFilter] = React.useState("ALL");

  const RunArtifacts = buildRunArtifacts(RunData.runs);
  const RunSummary = buildRunSummary(RunData.runs, RunArtifacts);
  const WarningGroups = buildWarningGroups(RunData.runs);
  const runTypes = ["ALL", ...Array.from(new Set(RunData.runs.map((r) => r.runType)))];
  const closedStages = RunData.stages.filter((s) => s.status === "closed").length;

  let rows = [...RunData.runs];
  if (statusFilter !== "ALL") rows = rows.filter((r) => r.status === statusFilter);
  if (typeFilter !== "ALL") rows = rows.filter((r) => r.runType === typeFilter);
  if (stageFilter !== "ALL") rows = rows.filter((r) => r.stage === stageFilter);

  const totalWarnings = Object.values(WarningGroups).reduce((s, a) => s + a.length, 0);

  return (
    <div className="live-page">
      {/* Header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Operational Audit</div>
          <h1 className="live-h1">
            Runs
            <span className="live-pulse"><PulseDot /> latest · {RunData.runs.length ? RunData.runs[0].started : "—"} ago</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <span className="meta-chunk"><span className="meta-k">artifacts</span><span className="meta-v">{RunArtifacts.length}</span></span>
          <span className="meta-chunk"><span className="meta-k">manifest</span><span className="meta-v ok">verified</span></span>
        </div>
      </div>

      {/* Stage Timeline */}
      <Card
        eyebrow="00 · Roadmap"
        title="Stage Timeline"
        right={<span className="meta-chunk"><span className="meta-k">closed</span><span className="meta-v ok">{closedStages} / {RunData.stages.length}</span></span>}
      >
        <div className="stage-track">
          {RunData.stages.map((s, i) => (
            <React.Fragment key={s.id}>
              <div
                className={"stage-node stage-" + s.status + (stageFilter === s.label ? " stage-active" : "")}
                onClick={() => setStageFilter(stageFilter === s.label ? "ALL" : s.label)}
              >
                <div className="stage-dot">
                  {s.status === "closed" ? "✓" : s.status === "review" ? "◐" : "·"}
                </div>
                <div className="stage-meta">
                  <div className="stage-label mono">{s.label}</div>
                  <div className="stage-title">{s.title}</div>
                  <div className={"stage-status stage-status-" + s.status}>
                    {s.statusLabel || (s.status === "closed" ? "Closed" : s.status === "review" ? "In review" : "Next")}
                  </div>
                </div>
              </div>
              {i < RunData.stages.length - 1 && (
                <div className={"stage-conn " + (s.status === "closed" ? "stage-conn-closed" : "")}/>
              )}
            </React.Fragment>
          ))}
        </div>
      </Card>

      {/* Summary strip */}
      <div className="cand-summary out-summary runs-summary">
        {RunSummary.map((s, i) => (
          <div key={i} className={"cand-tile cand-tile-" + (s.tone || "info")}>
            <div className="cand-tile-val">{s.value}</div>
            <div className="cand-tile-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="dec-filter-row">
        <div className="dec-filter-group">
          <span className="dec-filter-label">Status</span>
          {["ALL","PASS","WARN","PARTIAL","FAIL"].map((f) => (
            <span key={f} className={"filter-chip " + (statusFilter === f ? "active" : "")} onClick={() => setStatusFilter(f)}>
              {f === "ALL" ? "All" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Type</span>
          {runTypes.map((f) => (
            <span key={f} className={"filter-chip " + (typeFilter === f ? "active" : "")} onClick={() => setTypeFilter(f)}>
              {f === "ALL" ? "All" : f}
            </span>
          ))}
        </div>
        <div className="dec-filter-group">
          <span className="dec-filter-label">Stage</span>
          {["ALL", ...RunData.stages.map((s) => s.label)].map((f) => (
            <span key={f} className={"filter-chip " + (stageFilter === f ? "active" : "")} onClick={() => setStageFilter(f)}>
              {f === "ALL" ? "Any" : f.replace("Stage ", "S")}
            </span>
          ))}
        </div>
      </div>

      {/* Run Ledger */}
      <Card
        eyebrow="01 · Ledger"
        title="Run Ledger"
        right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{rows.length}</span></span>}
      >
        <div className="tbl-wrap">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Stage</th>
                <th>Type</th>
                <th>Started</th>
                <th className="num">Duration</th>
                <th>Status</th>
                <th>Inputs</th>
                <th>Outputs</th>
                <th className="num">Artifacts</th>
                <th className="num">Rows / Events</th>
                <th className="num">Warn</th>
                <th>Manifest</th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && (
                <tr><td colSpan="12"><div className="empty-state">No runs recorded yet</div></td></tr>
              )}
              {rows.map((r) => (
                <tr key={r.id} onClick={() => setSelected(r)} className={selected && selected.id === r.id ? "row-active" : ""}>
                  <td className="run-id mono">{r.id}</td>
                  <td><span className="stage-chip mono">{r.stage}</span></td>
                  <td><RunTypePill value={r.runType} /></td>
                  <td>
                    <div className="dec-time-rel mono">{r.started}</div>
                    <div className="dec-time-abs mono mute">{r.startedAbs}</div>
                  </td>
                  <td className="num mono">{r.duration}</td>
                  <td><RunStatusPill value={r.status} /></td>
                  <td className="ev-cell mono mute">{r.inputs}</td>
                  <td className="ev-cell mono">{r.outputs}</td>
                  <td className="num mono">{r.artifactsCount}</td>
                  <td className="num mono mute">{r.rows}</td>
                  <td className={"num mono " + (r.warnings ? "warn" : "")}>{r.warnings}</td>
                  <td><Hash value={r.manifestHash} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Artifacts + Warnings */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="02 · Artifacts"
          title="Artifact Browser"
          right={<span className="meta-chunk"><span className="meta-k">total</span><span className="meta-v">{RunArtifacts.length}</span></span>}
        >
          <div className="tbl-wrap">
            <table className="tbl tbl-clickable">
              <thead>
                <tr>
                  <th>Artifact</th>
                  <th>Type</th>
                  <th>Stage</th>
                  <th className="num">Rows</th>
                  <th>Created</th>
                  <th>Hash</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {RunArtifacts.length === 0 && (
                  <tr><td colSpan="7"><div className="empty-state">No artifacts present</div></td></tr>
                )}
                {RunArtifacts.slice(0, 24).map((a) => (
                  <tr key={a.id} onClick={() => setSelected(RunData.runs.find((r) => r.id === a.runId))}>
                    <td className="art-name mono">{a.name}</td>
                    <td><span className="art-type-chip">{a.type}</span></td>
                    <td><span className="stage-chip mono">{a.stage}</span></td>
                    <td className="num mono mute">{a.rows}</td>
                    <td className="mono mute">{a.created}</td>
                    <td><Hash value={a.hash} /></td>
                    <td><span className={"pill pill-" + (a.status === "OK" ? "ok" : a.status === "WARN" ? "warn" : "bad") + " pill-dim"}>{a.status}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card
          eyebrow="03 · Issues"
          title="Warnings / Failures"
          right={<span className="meta-chunk"><span className="meta-k">total</span><span className="meta-v" style={{color: totalWarnings ? "#ffc873" : "#7df0a4"}}>{totalWarnings}</span></span>}
        >
          {totalWarnings === 0 ? (
            <div className="empty-state">No warnings or failures.</div>
          ) : (
            <div className="warn-groups">
              {Object.entries(WarningGroups).map(([name, runs]) => {
                if (!runs.length) return null;
                return (
                  <div key={name} className="warn-group">
                    <div className="warn-group-hd">
                      <span className="warn-group-name">{name}</span>
                      <span className="warn-group-count">{runs.length}</span>
                    </div>
                    <div className="warn-group-rows">
                      {runs.map((r, i) => (
                        <div key={i} className="warn-group-row" onClick={() => setSelected(r)}>
                          <span className="run-id mono">{r.id}</span>
                          <RunStatusPill value={r.status} />
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <div className="live-foot">
        <span className="foot-mute">{live ? "artifact-backed" : "Front-end mock"} · read-only · runs are immutable</span>
        <span className="foot-mute foot-pulse"><PulseDot /> audit trail</span>
      </div>

      <RunDrawer run={selected} onClose={() => setSelected(null)} allArtifacts={RunArtifacts} />
    </div>
  );
}

window.RunsPage = RunsPage;
