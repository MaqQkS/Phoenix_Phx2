// Phoenix dashboard — original UI inspired by the layout brief.
// Top bar with branded left (logo + ember-gradient wordmark),
// centered nav across 9 tabs, utility cluster on the right.
// Tab content intentionally blank; nav is the only interaction.

// Portfolio + XScanner are not designed in the handoff — hidden as future work.
const TABS = [
"Live",
"Paper",
"Candidates",
"Decisions",
"Outcomes",
"Calibration",
"Runs",
"Research"];


// PHX2 perf pass: animated ember particles + flying phoenix removed — the
// top bar is now fully static so 10s polling never fights continuous repaints.
const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "navStyle": "underline",
  "wordmark": "gradient",
  "glow": 0.75,
  "watermark": false,
  "showHint": true
} /*EDITMODE-END*/;

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="7" cy="7" r="5" />
      <path d="M11 11l3 3" strokeLinecap="round" />
    </svg>);

}
function ChevronIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 4.5L6 7.5L9 4.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>);

}
function StarIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 1.6l1.9 3.9 4.3.6-3.1 3 .7 4.3L8 11.4 4.2 13.4l.7-4.3-3.1-3 4.3-.6L8 1.6z" strokeLinejoin="round" />
    </svg>);

}
function WalletIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="4" width="12" height="9" rx="2" />
      <path d="M2 7h12" />
      <circle cx="11" cy="10" r="0.8" fill="currentColor" stroke="none" />
    </svg>);

}
function BellIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 11V7a4 4 0 1 1 8 0v4l1 1.5H3L4 11z" strokeLinejoin="round" />
      <path d="M6.5 13.5a1.5 1.5 0 0 0 3 0" />
    </svg>);

}

function App() {
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [tab, setTab] = React.useState("Live");

  React.useEffect(() => {
    // restore last tab
    const saved = localStorage.getItem("phoenix.tab");
    if (saved && TABS.includes(saved)) setTab(saved);
  }, []);
  React.useEffect(() => {
    localStorage.setItem("phoenix.tab", tab);
  }, [tab]);

  return (
    <>
      <header className="topbar" style={{ ["--logo-glow"]: t.glow }}>
        {/* LEFT — brand (static: no ember field, no flying phoenix) */}
        <div className="brand">
          <span className="brand-logo">
            <img src="assets/phoenix-logo-transparent.png" alt="" />
          </span>
          <span style={{ position: "relative", display: "inline-block" }}>
            <span className={"wordmark " + (t.wordmark === "solid" ? "solid" : t.wordmark === "outline" ? "outline" : "")} style={{ fontFamily: "Inter" }}>
              PHOENIX
            </span>
          </span>
        </div>

        {/* CENTER — nav */}
        <nav className={"nav " + (t.navStyle === "pill" ? "pill" : "")}>
          {TABS.map((name) =>
          <button
            key={name}
            className={"nav-item " + (tab === name ? "active" : "")}
            onClick={() => setTab(name)}>

              {name}
            </button>
          )}
        </nav>

        {/* RIGHT — utility */}
        <div className="util">
          <div className="chain" title="Solana">
            <span className="sol-mark" />
            <span>SOL</span>
            <ChevronIcon />
          </div>
          <div className="search">
            <SearchIcon />
            <input placeholder="Search tokens, wallets, runs…" />
            <span className="kbd">/</span>
          </div>
          <div className="icon-btn" title="Notifications"><BellIcon /></div>
        </div>
      </header>

      <main>
        <div className={"watermark " + (t.watermark ? "on" : "")}>
          <img src="assets/phoenix-logo-transparent.png" alt="" />
        </div>
        {tab === "Live" ?
        <LivePage /> :
        tab === "Paper" ?
        <PaperPage /> :
        tab === "Candidates" ?
        <CandidatesPage /> :
        tab === "Decisions" ?
        <DecisionsPage /> :
        tab === "Outcomes" ?
        <OutcomesPage /> :
        tab === "Calibration" ?
        <CalibrationPage /> :
        tab === "Runs" ?
        <RunsPage /> :
        tab === "Research" ?
        <ResearchPage /> :

        <div className={"hint " + (t.showHint ? "on" : "")}>
            <b>{tab}</b>
          </div>
        }
      </main>

      <TweaksPanel>
        <TweakSection label="Brand" />
        <TweakRadio
          label="Wordmark"
          value={t.wordmark}
          options={["gradient", "solid", "outline"]}
          onChange={(v) => setTweak("wordmark", v)} />

        <TweakSlider
          label="Logo glow"
          value={t.glow}
          min={0}
          max={1.2}
          step={0.05}
          onChange={(v) => setTweak("glow", v)} />

        <TweakSection label="Navigation" />
        <TweakRadio
          label="Active style"
          value={t.navStyle}
          options={["underline", "pill"]}
          onChange={(v) => setTweak("navStyle", v)} />


        <TweakSection label="Page" />
        <TweakToggle
          label="Phoenix watermark"
          value={t.watermark}
          onChange={(v) => setTweak("watermark", v)} />

        <TweakToggle
          label="Show tab name (placeholder)"
          value={t.showHint}
          onChange={(v) => setTweak("showHint", v)} />

      </TweaksPanel>

      <DataSourceBadge />
    </>);

}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);