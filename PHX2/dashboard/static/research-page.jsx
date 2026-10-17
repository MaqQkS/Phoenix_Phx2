// Phoenix — Research page (cohort studies, hypotheses, weird cases)
// Static mock data only. Read-only.

const ResearchData = {
  studies: [
    {
      id: "STUDY-001", title: "SOL vs USDC Outcomes",
      question: "Do USDC-pair launches need separate calibration?",
      cohort: "USDC observe-only", sampleSize: 34,
      status: "COLLECTING_DATA", signal: "MIXED", confidence: "MEDIUM",
      lastUpdated: "3h ago", nextStep: "Collect more USDC outcomes",
      findings: "USDC bounces look attenuated vs SOL — but n=34 is below the calibration floor. Holding observe-only until n≥80.",
    },
    {
      id: "STUDY-002", title: "Bundle Risk Study",
      question: "Do BUNDLE_RISK skips mostly die?",
      cohort: "BUNDLE_RISK skips", sampleSize: 82,
      status: "READY_FOR_REVIEW", signal: "STRONG", confidence: "HIGH",
      lastUpdated: "1d ago", nextStep: "Review missed runners",
      findings: "78% of bundle-risk skips died or decayed within 6h. 7 missed runners under review — likely organic-looking bundles.",
    },
    {
      id: "STUDY-003", title: "ATH Unknown Study",
      question: "Are ATH_UNKNOWN skips hiding missed runners?",
      cohort: "ATH_UNKNOWN skips", sampleSize: 41,
      status: "BLOCKED", signal: "DATA_BLOCKED", confidence: "LOW",
      lastUpdated: "5h ago", nextStep: "Improve ATH measurement",
      findings: "Cannot answer the question without a confirmed ATH for the cohort. Awaiting Stage 25b ATH backfill.",
    },
    {
      id: "STUDY-004", title: "Low Liquidity Study",
      question: "Does low liquidity predict dead charts?",
      cohort: "LOW_LIQUIDITY skips", sampleSize: 66,
      status: "ACTIVE", signal: "MODERATE", confidence: "MEDIUM",
      lastUpdated: "2h ago", nextStep: "Label edge cases",
      findings: "73% of LOW_LIQUIDITY skips decayed further, but 9% bounced strongly (GIGA pattern). Filter is useful but not absolute.",
    },
    {
      id: "STUDY-005", title: "Tier Timing Study",
      question: "Are Tier 1 alerts too early or too late?",
      cohort: "WOULD_ALERT Tier 1", sampleSize: 53,
      status: "OPEN", signal: "UNKNOWN", confidence: "LOW",
      lastUpdated: "6h ago", nextStep: "Compare bounce timing",
      findings: "Median time-to-bounce 42m, but variance is high. Need to split by migration age.",
    },
    {
      id: "STUDY-006", title: "Migration Age Study",
      question: "Does migration age below 1h predict failure?",
      cohort: "MIGRATION_TOO_FRESH skips", sampleSize: 22,
      status: "NEEDS_LABELS", signal: "WEAK", confidence: "LOW",
      lastUpdated: "11h ago", nextStep: "Manually label 22 fresh migrations",
      findings: "Too small a sample to commit; labeling round in progress.",
    },
    {
      id: "STUDY-007", title: "Holder Concentration Study",
      question: "Does top-10 holder share > 35% predict bundle behavior?",
      cohort: "All decisions", sampleSize: 312,
      status: "ACTIVE", signal: "MODERATE", confidence: "MEDIUM",
      lastUpdated: "30m ago", nextStep: "Correlate with bundle-risk filter",
      findings: "Holder share > 35% co-occurs with bundle-risk 68% of the time. Possible redundancy — investigate.",
    },
    {
      id: "STUDY-008", title: "Filter Precision Study",
      question: "Which filters produce the most false negatives?",
      cohort: "All SKIP decisions", sampleSize: 184,
      status: "READY_FOR_REVIEW", signal: "STRONG", confidence: "HIGH",
      lastUpdated: "1h ago", nextStep: "Approve Stage 26 review packet",
      findings: "False-negative rate by filter: BUNDLE_RISK 8.5%, LOW_LIQ 9.1%, BELOW_TIER 17.4%. Below-tier is the weakest filter.",
    },
    {
      id: "STUDY-009", title: "Dead Chart Detection Study",
      question: "Is the DEAD_CHART_PATTERN detector over- or under-firing?",
      cohort: "DEAD_CHART skips", sampleSize: 18,
      status: "CLOSED", signal: "STRONG", confidence: "HIGH",
      lastUpdated: "3d ago", nextStep: "—",
      findings: "94% confirmed dead within 24h. Zero recoveries. Detector closed as production-quality.",
    },
  ],

  cohorts: [
    { id: "co1", name: "WOULD_ALERT · SOL · T1", count: 26, hit: 67, miss: 22, saved: 0, missedRunner: 0, censored: 11, medBounce: "+82%", medDraw: "-58%", confidence: "HIGH" },
    { id: "co2", name: "WOULD_ALERT · SOL · T2", count: 18, hit: 55, miss: 28, saved: 0, missedRunner: 0, censored: 17, medBounce: "+44%", medDraw: "-52%", confidence: "MEDIUM" },
    { id: "co3", name: "SKIP · BUNDLE_RISK · SOL", count: 82, hit: 0, miss: 0, saved: 78, missedRunner: 8, censored: 14, medBounce: "-12%", medDraw: "-71%", confidence: "HIGH" },
    { id: "co4", name: "SKIP · ATH_UNKNOWN · SOL", count: 41, hit: 0, miss: 0, saved: 0, missedRunner: 0, censored: 100, medBounce: "—", medDraw: "—", confidence: "LOW" },
    { id: "co5", name: "OBSERVE_ONLY · USDC", count: 34, hit: 0, miss: 0, saved: 0, missedRunner: 0, censored: 67, medBounce: "+22%", medDraw: "-31%", confidence: "MEDIUM" },
    { id: "co6", name: "SKIP · LOW_LIQUIDITY · SOL", count: 66, hit: 0, miss: 0, saved: 73, missedRunner: 9, censored: 18, medBounce: "-8%", medDraw: "-64%", confidence: "MEDIUM" },
    { id: "co7", name: "WATCH · SOL", count: 28, hit: 32, miss: 0, saved: 0, missedRunner: 0, censored: 29, medBounce: "+18%", medDraw: "-42%", confidence: "MEDIUM" },
    { id: "co8", name: "SKIP · DEAD_CHART · SOL", count: 18, hit: 0, miss: 0, saved: 94, missedRunner: 0, censored: 6, medBounce: "-9%", medDraw: "-95%", confidence: "HIGH" },
  ],

  filterStudies: [
    { name: "Bundle Risk", triggered: 82, saved: 64, missed: 7, censored: 11, confidence: "HIGH", note: "Strong reject signal, but review false negatives." },
    { name: "Low Liquidity", triggered: 66, saved: 48, missed: 6, censored: 12, confidence: "MEDIUM", note: "Promising but needs more labeled examples." },
    { name: "Holder Concentration", triggered: 38, saved: 28, missed: 4, censored: 6, confidence: "MEDIUM", note: "Useful, but partially redundant with bundle risk." },
    { name: "Price Stale", triggered: 24, saved: 0, missed: 0, censored: 24, confidence: "LOW", note: "Pure data issue — outcome cannot be measured under this filter." },
    { name: "ATH Unknown", triggered: 41, saved: 0, missed: 0, censored: 41, confidence: "LOW", note: "Blocks measurement entirely; not a real reject signal." },
    { name: "USDC Pair", triggered: 34, saved: 0, missed: 0, censored: 0, confidence: "MEDIUM", note: "Different lane — keep observe-only until separate calibration exists." },
    { name: "Dead Chart Pattern", triggered: 18, saved: 17, missed: 0, censored: 1, confidence: "HIGH", note: "Production-quality detector; zero false negatives in sample." },
    { name: "Filter Incomplete", triggered: 9, saved: 0, missed: 0, censored: 9, confidence: "LOW", note: "Outcome cannot be measured; treat as operational warning." },
  ],

  uglyCases: {
    "Skipped then ran": [
      { token: "BRETT",  pair: "BRETT / SOL",  decision: "SKIP", outcome: "MISSED_RUNNER", why: "Below-tier threshold then ran +147%.", status: "OPEN" },
      { token: "BRETT2", pair: "BRETT2 / SOL", decision: "SKIP", outcome: "MISSED_RUNNER", why: "Skipped at -44%, ran +147% after deeper drawdown.", status: "OPEN" },
      { token: "GIGA",   pair: "GIGA / SOL",   decision: "SKIP", outcome: "MISSED_RUNNER", why: "LOW_LIQ at decision, liquidity recovered post-skip.", status: "OPEN" },
    ],
    "Would-alert then died": [
      { token: "GOAT", pair: "GOAT / SOL", decision: "WOULD_ALERT", outcome: "MISS", why: "+12% bounce stalled, then -68% structural failure.", status: "ACTIVE" },
    ],
    "ATH unknown but later clean": [
      { token: "BONK", pair: "BONK / SOL", decision: "SKIP", outcome: "CENSORED", why: "ATH later confirmed by Birdeye backfill — recoverable.", status: "BLOCKED" },
      { token: "CASH", pair: "CASH / SOL", decision: "SKIP", outcome: "CENSORED", why: "ATH confirmation pending Stage 25b backfill.", status: "BLOCKED" },
    ],
    "USDC pair went nuclear": [
      { token: "WIF", pair: "WIF / USDC", decision: "OBSERVE_ONLY", outcome: "PARTIAL", why: "+31% bounce on uncalibrated USDC lane.", status: "COLLECTING" },
    ],
    "Bundle risk but organic-looking": [
      { token: "CHILL", pair: "CHILL / SOL", decision: "WOULD_ALERT", outcome: "PENDING", why: "Bundle risk 0.31 (borderline) — organic surface signals.", status: "NEEDS_LABELS" },
    ],
    "Low liquidity but strong bounce": [
      { token: "GIGA", pair: "GIGA / SOL", decision: "SKIP", outcome: "MISSED_RUNNER", why: "Liq $182K at decision, ran +94% after liquidity recovery.", status: "OPEN" },
    ],
    "Censored / partial measurement": [
      { token: "MOG",  pair: "MOG / SOL",  decision: "SKIP", outcome: "NO_DATA",  why: "Price feed stale throughout outcome window.", status: "BLOCKED" },
      { token: "BORK", pair: "BORK / SOL", decision: "SKIP", outcome: "CENSORED", why: "Filter set never completed.", status: "BLOCKED" },
    ],
    "Filter disagreement": [
      { token: "GIGA", pair: "GIGA / SOL", decision: "SKIP", outcome: "MISSED_RUNNER", why: "Manual label LOW_QUALITY but evidence suggests REVIEW.", status: "OPEN" },
    ],
  },

  questions: [
    { q: "Do USDC pairs need separate tier thresholds?", status: "COLLECTING_DATA", last: "3h" },
    { q: "Is ATH_UNKNOWN mostly data failure or low-quality token behavior?", status: "BLOCKED", last: "5h" },
    { q: "Does BUNDLE_RISK have enough precision to become enforcement later?", status: "READY_FOR_REVIEW", last: "1d" },
    { q: "Are Tier 1 alerts too early or too late?", status: "OPEN", last: "6h" },
    { q: "Does low liquidity block too many runners?", status: "ACTIVE", last: "2h" },
    { q: "Are skips saving us more than they cost us?", status: "NEEDS_LABELS", last: "11h" },
    { q: "Which filters create the most false negatives?", status: "READY_FOR_REVIEW", last: "1h" },
    { q: "Is the DEAD_CHART_PATTERN detector calibrated correctly?", status: "CLOSED", last: "3d" },
  ],

  findings: [
    { title: "Bundle-risk skips", body: "Mostly saved-by-skip in current sample (78%), but missed runners need review. Detector quality looks strong; precision still needs human verification." },
    { title: "USDC pairs", body: "Show different behavior from SOL pairs — bounces attenuated, drawdowns shallower. Keep observe-only until separate calibration exists." },
    { title: "ATH_UNKNOWN", body: "Should not count as wins or misses. Classify as censored until measurable. Awaiting Stage 25b ATH backfill." },
    { title: "Low-liquidity blocks", body: "Promising signal (73% saved) but the GIGA-pattern false-negatives suggest a more nuanced liquidity-recovery filter is worth exploring." },
  ],
};

// ─── Tones ───────────────────────────────────────────────────────────
const studyStatusTone = {
  OPEN: "muted",
  ACTIVE: "ember",
  COLLECTING_DATA: "ember",
  NEEDS_LABELS: "warn",
  READY_FOR_REVIEW: "ok",
  BLOCKED: "bad",
  CLOSED: "muted",
  COLLECTING: "ember",
};
const signalTone = {
  STRONG: "ok",
  MODERATE: "ember",
  WEAK: "muted",
  MIXED: "warn",
  DATA_BLOCKED: "bad",
  UNKNOWN: "muted",
};

function StudyStatusPill({ value }) {
  return <span className={"pill pill-" + (studyStatusTone[value] || "muted")}>{value}</span>;
}
function SignalPill({ value }) {
  return <span className={"pill pill-" + (signalTone[value] || "muted") + " pill-dim"}>{value}</span>;
}

// ─── Drawer ──────────────────────────────────────────────────────────
function StudyDrawer({ study, onClose }) {
  if (!study) return null;
  return (
    <>
      <div className="cd-scrim" onClick={onClose} />
      <aside className="cd-drawer">
        <div className="cd-hd">
          <div>
            <div className="cd-eyebrow">Study Detail · {study.id}</div>
            <div className="cd-title">
              <span className="cd-sym" style={{ fontSize: 18 }}>{study.title}</span>
            </div>
            <div className="cd-addr">{study.cohort} · n={study.sampleSize}</div>
          </div>
          <button className="cd-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="cd-stage-banner">
          <StudyStatusPill value={study.status} />
          <SignalPill value={study.signal} />
          <ConfidenceChip value={study.confidence} />
          <span className="cd-banner-update meta-chunk">
            <span className="meta-k">updated</span>
            <span className="meta-v">{study.lastUpdated}</span>
          </span>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Research Question</div>
          <p className="cd-note" style={{ fontSize: 14, lineHeight: 1.55, fontStyle: "italic" }}>"{study.question}"</p>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Study Context</div>
          <div className="cd-grid">
            <div className="cd-kv"><span>Cohort</span><b className="mono">{study.cohort}</b></div>
            <div className="cd-kv"><span>Sample size</span><b className="mono ember">n={study.sampleSize}</b></div>
            <div className="cd-kv"><span>Status</span><b><StudyStatusPill value={study.status} /></b></div>
            <div className="cd-kv"><span>Signal</span><b><SignalPill value={study.signal} /></b></div>
            <div className="cd-kv"><span>Confidence</span><b><ConfidenceChip value={study.confidence} /></b></div>
            <div className="cd-kv"><span>Last updated</span><b className="mono">{study.lastUpdated}</b></div>
          </div>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Findings</div>
          <p className="cd-note">{study.findings}</p>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Next Step</div>
          <p className="cd-note cd-note-warn">→ {study.nextStep}</p>
        </div>

        <div className="cd-section">
          <div className="cd-section-hd">Cross-references</div>
          <div className="xref">
            <span className="xref-link">→ View cohort in <b>Outcomes</b></span>
            <span className="xref-link">→ View labels in <b>Calibration</b></span>
            <span className="xref-link">→ View source runs in <b>Runs</b></span>
          </div>
        </div>

        <div className="cd-foot">
          <span className="foot-mute">research-only · findings do not affect live decisions</span>
        </div>
      </aside>
    </>
  );
}

// ─── Cohort Explorer ─────────────────────────────────────────────────
function CohortExplorer() {
  const [pair, setPair] = React.useState("ALL");
  const [decision, setDecision] = React.useState("ALL");
  const [reason, setReason] = React.useState("ALL");
  const [outcome, setOutcome] = React.useState("ALL");
  const [quality, setQuality] = React.useState("ALL");
  const [manual, setManual] = React.useState("ALL");

  // For the mock, we always show the precomputed cohorts; filters are visual only.
  return (
    <Card
      eyebrow="02 · Cohort Explorer"
      title="Group Comparison"
      right={<span className="meta-chunk"><span className="meta-k">cohorts</span><span className="meta-v">{ResearchData.cohorts.length}</span></span>}
    >
      <div className="cohort-controls">
        <Selector label="pair" value={pair} options={["ALL","SOL","USDC","UNKNOWN"]} onChange={setPair} />
        <Selector label="decision" value={decision} options={["ALL","WOULD_ALERT","SKIP","OBSERVE_ONLY","WATCH"]} onChange={setDecision} />
        <Selector label="reason" value={reason} options={["ALL","BUNDLE_RISK","ATH_UNKNOWN","PRICE_STALE","LOW_LIQUIDITY","USDC_PAIR_OBSERVE_ONLY"]} onChange={setReason} />
        <Selector label="outcome" value={outcome} options={["ALL","HIT","MISS","SAVED_BY_SKIP","MISSED_RUNNER","CENSORED","PARTIAL","DEAD"]} onChange={setOutcome} />
        <Selector label="quality" value={quality} options={["ALL","COMPLETE","PARTIAL","STALE","MISSING_ATH"]} onChange={setQuality} />
        <Selector label="label" value={manual} options={["ALL","ORGANIC","BUNDLED","WASHY","RUG","AMBIGUOUS","EXCLUDE"]} onChange={setManual} />
      </div>
      <div className="research-banner" style={{ marginBottom: 10 }}>
        <span className="research-banner-icon">i</span>
        <span>Numbers shown are <b>upstream-precomputed</b>. Filters are visual aids — Research must never compute aggregates in the frontend.</span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Cohort</th>
              <th className="num">Count</th>
              <th className="num">Hit %</th>
              <th className="num">Miss %</th>
              <th className="num">Saved %</th>
              <th className="num">Missed Runner %</th>
              <th className="num">Censored %</th>
              <th className="num">Med. Bounce</th>
              <th className="num">Med. Drawdown</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {ResearchData.cohorts.map((c) => (
              <tr key={c.id}>
                <td><span className="mono ember">{c.name}</span></td>
                <td className="num mono">{c.count}</td>
                <td className="num mono ok">{c.hit ? c.hit + "%" : "—"}</td>
                <td className="num mono warn">{c.miss ? c.miss + "%" : "—"}</td>
                <td className="num mono ok">{c.saved ? c.saved + "%" : "—"}</td>
                <td className="num mono warn">{c.missedRunner ? c.missedRunner + "%" : "—"}</td>
                <td className="num mono mute">{c.censored ? c.censored + "%" : "—"}</td>
                <td className={"num mono " + (c.medBounce.startsWith("+") ? "ok" : c.medBounce === "—" ? "mute" : "warn")}>{c.medBounce}</td>
                <td className="num mono warn">{c.medDraw}</td>
                <td><ConfidenceChip value={c.confidence} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ─── Page ────────────────────────────────────────────────────────────
function ResearchPage() {
  const [selected, setSelected] = React.useState(null);
  const [statusFilter, setStatusFilter] = React.useState("ALL");

  let studies = [...ResearchData.studies];
  if (statusFilter !== "ALL") studies = studies.filter((s) => s.status === statusFilter);

  const Summary = [
    { label: "Studies", value: ResearchData.studies.length, tone: "info" },
    { label: "Open Questions", value: ResearchData.questions.filter((q) => q.status !== "CLOSED").length, tone: "ember" },
    { label: "Active Cohorts", value: ResearchData.cohorts.length, tone: "watching" },
    { label: "Ugly Cases", value: Object.values(ResearchData.uglyCases).reduce((s,a) => s + a.length, 0), tone: "warn" },
    { label: "SOL vs USDC", value: ResearchData.studies.filter((s) => /USDC/.test(s.title)).length, tone: "watching" },
    { label: "Filter Studies", value: ResearchData.filterStudies.length, tone: "ember" },
    { label: "False Negatives", value: ResearchData.filterStudies.reduce((s,f) => s + (f.missed || 0), 0), tone: "bad" },
    { label: "Ready for Review", value: ResearchData.studies.filter((s) => s.status === "READY_FOR_REVIEW").length, tone: "ok" },
    { label: "Blocked by Data", value: ResearchData.studies.filter((s) => s.status === "BLOCKED" || s.signal === "DATA_BLOCKED").length, tone: "bad" },
  ];

  return (
    <div className="live-page">
      <DemoDataBanner>
        Research is a future page — no real study artifacts exist yet. Showing the design demo dataset (not PHX2 data).
      </DemoDataBanner>
      {/* Header */}
      <div className="live-head">
        <div>
          <div className="live-eyebrow">Research Lab</div>
          <h1 className="live-h1">
            Research
            <span className="live-pulse"><PulseDot /> {ResearchData.studies.length} studies · {ResearchData.questions.filter((q) => q.status !== "CLOSED").length} open</span>
          </h1>
        </div>
        <div className="live-head-meta">
          <span className="meta-chunk"><span className="meta-k">ready</span><span className="meta-v ok">{ResearchData.studies.filter((s) => s.status === "READY_FOR_REVIEW").length}</span></span>
          <span className="meta-chunk"><span className="meta-k">blocked</span><span className="meta-v" style={{color:"#ff8a7a"}}>{ResearchData.studies.filter((s) => s.status === "BLOCKED").length}</span></span>
        </div>
      </div>

      {/* Summary strip */}
      <div className="cand-summary out-summary runs-summary">
        {Summary.map((s, i) => (
          <div key={i} className={"cand-tile cand-tile-" + (s.tone || "info")}>
            <div className="cand-tile-val">{s.value}</div>
            <div className="cand-tile-lbl">{s.label}</div>
          </div>
        ))}
      </div>

      {/* Study Board */}
      <div className="dec-filter-row">
        <div className="dec-filter-group">
          <span className="dec-filter-label">Status</span>
          {["ALL","OPEN","ACTIVE","COLLECTING_DATA","NEEDS_LABELS","READY_FOR_REVIEW","BLOCKED","CLOSED"].map((f) => (
            <span key={f} className={"filter-chip " + (statusFilter === f ? "active" : "")} onClick={() => setStatusFilter(f)}>
              {f === "ALL" ? "All" : f}
            </span>
          ))}
        </div>
      </div>

      <Card
        eyebrow="01 · Studies"
        title="Research Study Board"
        right={<span className="meta-chunk"><span className="meta-k">rows</span><span className="meta-v">{studies.length}</span></span>}
      >
        <div className="tbl-wrap">
          <table className="tbl tbl-clickable">
            <thead>
              <tr>
                <th>Study</th>
                <th>Research Question</th>
                <th>Cohort</th>
                <th className="num">n</th>
                <th>Status</th>
                <th>Signal</th>
                <th>Confidence</th>
                <th>Last Updated</th>
                <th>Next Step</th>
              </tr>
            </thead>
            <tbody>
              {studies.map((s) => (
                <tr key={s.id} onClick={() => setSelected(s)} className={selected && selected.id === s.id ? "row-active" : ""}>
                  <td><span className="mono ember">{s.title}</span></td>
                  <td className="ev-cell" style={{ fontStyle: "italic", color: "var(--txt)", maxWidth: 320 }}>"{s.question}"</td>
                  <td className="mono mute">{s.cohort}</td>
                  <td className="num mono">{s.sampleSize}</td>
                  <td><StudyStatusPill value={s.status} /></td>
                  <td><SignalPill value={s.signal} /></td>
                  <td><ConfidenceChip value={s.confidence} /></td>
                  <td className="mono mute">{s.lastUpdated}</td>
                  <td className="ev-cell">{s.nextStep}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Cohort Explorer */}
      <CohortExplorer />

      {/* Filter Studies */}
      <Card
        eyebrow="03 · Filters"
        title="Filter Study Panel"
        right={<span className="meta-chunk"><span className="meta-k">filters</span><span className="meta-v">{ResearchData.filterStudies.length}</span></span>}
      >
        <div className="filter-study-grid">
          {ResearchData.filterStudies.map((f) => (
            <div key={f.name} className="filter-study">
              <div className="filter-study-hd">
                <span className="filter-study-name">{f.name}</span>
                <ConfidenceChip value={f.confidence} />
              </div>
              <div className="filter-study-stats">
                <div className="fs-stat"><span className="fs-stat-l">triggered</span><span className="fs-stat-v mono">{f.triggered}</span></div>
                <div className="fs-stat"><span className="fs-stat-l">saved</span><span className="fs-stat-v mono ok">{f.saved}</span></div>
                <div className="fs-stat"><span className="fs-stat-l">missed</span><span className="fs-stat-v mono warn">{f.missed}</span></div>
                <div className="fs-stat"><span className="fs-stat-l">censored</span><span className="fs-stat-v mono mute">{f.censored}</span></div>
              </div>
              <div className="filter-study-bar">
                {f.triggered > 0 && (
                  <>
                    <span className="fs-bar-seg fs-bar-ok" style={{ flex: f.saved }} />
                    <span className="fs-bar-seg fs-bar-bad" style={{ flex: f.missed }} />
                    <span className="fs-bar-seg fs-bar-muted" style={{ flex: f.censored }} />
                  </>
                )}
              </div>
              <p className="filter-study-note">{f.note}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Ugly Cases */}
      <Card
        eyebrow="04 · Library"
        title="Weird / Ugly Case Library"
        right={<span className="meta-chunk"><span className="meta-k">cases</span><span className="meta-v">{Object.values(ResearchData.uglyCases).reduce((s,a) => s + a.length, 0)}</span></span>}
      >
        <div className="ugly-grid">
          {Object.entries(ResearchData.uglyCases).map(([name, items]) => (
            <div key={name} className="ugly-group">
              <div className="ugly-group-hd">
                <span className="ugly-group-name">{name}</span>
                <span className="ugly-group-count">{items.length}</span>
              </div>
              <div className="ugly-rows">
                {items.map((u, i) => (
                  <div key={i} className="ugly-card">
                    <div className="ugly-top">
                      <span className="tok-sym">{u.token}</span>
                      <span className="mono mute" style={{ fontSize: 11 }}>{u.pair}</span>
                    </div>
                    <div className="ugly-mid">
                      <Pill tone={decisionTone[u.decision] || "muted"} dim>{u.decision}</Pill>
                      <span className="ugly-arrow">→</span>
                      <OutcomePill value={u.outcome} />
                    </div>
                    <div className="ugly-why">{u.why}</div>
                    <div className="ugly-status mono">{u.status}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Questions + Findings */}
      <div className="live-row cand-bottom">
        <Card
          eyebrow="05 · Questions"
          title="Open Research Questions"
          right={<span className="meta-chunk"><span className="meta-k">open</span><span className="meta-v">{ResearchData.questions.filter((q) => q.status !== "CLOSED").length}</span></span>}
        >
          <div className="q-list">
            {ResearchData.questions.map((q, i) => (
              <div key={i} className="q-row">
                <span className="q-q">{q.q}</span>
                <div className="q-meta">
                  <StudyStatusPill value={q.status} />
                  <span className="mono mute" style={{ fontSize: 11 }}>{q.last} ago</span>
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card
          eyebrow="06 · Findings"
          title="Research Notes"
          right={<span className="meta-chunk"><span className="meta-k">notes</span><span className="meta-v">{ResearchData.findings.length}</span></span>}
        >
          <div className="findings-list">
            {ResearchData.findings.map((f, i) => (
              <div key={i} className="finding">
                <div className="finding-title">{f.title}</div>
                <div className="finding-body">{f.body}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="live-foot">
        <span className="foot-mute">Front-end mock · research-only · numbers are pre-computed upstream</span>
        <span className="foot-mute foot-pulse"><PulseDot /> research lab</span>
      </div>

      <StudyDrawer study={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

window.ResearchPage = ResearchPage;
