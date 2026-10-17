// Phoenix — PHX2 artifact data layer (READ-ONLY).
// Polls /api/xdata (served by PHX2/dashboard/server.py) and exposes:
//   usePhxData(key, mockFallback) — page data hook (live artifacts, else mock)
//   usePhxLive()                  — true when real artifact data is loaded
//   DataSourceBadge               — fixed badge labeling LIVE vs MOCK mode
// No writes, no dispatch — this file only ever issues GET /api/xdata.

const PHX_POLL_MS = 10000;

const PhxStore = {
  data: null, // full bundle from /api/xdata
  status: "loading", // "live" | "stale" | "mock" | "loading"
  error: null,
  lastFetchAt: null,
  listeners: new Set(),
};

function phxNotify() {
  PhxStore.listeners.forEach((fn) => {
    try { fn(); } catch (e) { /* listener gone */ }
  });
}

async function phxFetchOnce() {
  try {
    const res = await fetch("/api/xdata", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    PhxStore.data = await res.json();
    PhxStore.status = "live";
    PhxStore.error = null;
  } catch (err) {
    PhxStore.error = String((err && err.message) || err);
    PhxStore.status = PhxStore.data ? "stale" : "mock";
  }
  PhxStore.lastFetchAt = Date.now();
  phxNotify();
}

phxFetchOnce();
setInterval(phxFetchOnce, PHX_POLL_MS);

function usePhxSubscribe() {
  const [, force] = React.useReducer((x) => x + 1, 0);
  React.useEffect(() => {
    PhxStore.listeners.add(force);
    return () => PhxStore.listeners.delete(force);
  }, []);
}

// Page hook: live artifact data for `key`, else the design-mock fallback.
function usePhxData(key, mockFallback) {
  usePhxSubscribe();
  if (PhxStore.data && PhxStore.data[key] != null) return PhxStore.data[key];
  return mockFallback;
}

function usePhxLive() {
  usePhxSubscribe();
  return PhxStore.data != null;
}

function usePhxMeta() {
  usePhxSubscribe();
  return PhxStore.data ? PhxStore.data.meta : null;
}

function DataSourceBadge() {
  usePhxSubscribe();
  const st = PhxStore.status;
  const meta = PhxStore.data && PhxStore.data.meta;
  let cls, dot, label;
  if (st === "live") {
    cls = "phx-badge-live"; dot = "ok";
    label = "LIVE ARTIFACTS · read-only · poll " + PHX_POLL_MS / 1000 + "s";
  } else if (st === "stale") {
    cls = "phx-badge-stale"; dot = "warn";
    label = "LIVE (stale — last fetch failed)";
  } else if (st === "mock") {
    cls = "phx-badge-mock"; dot = "warn";
    label = "MOCK DATA · fallback (artifacts/API unavailable)";
  } else {
    cls = "phx-badge-mock"; dot = "info";
    label = "connecting to artifact feed…";
  }
  return (
    <div className={"phx-data-badge " + cls} title={meta ? ("generated " + meta.generated_at_utc + " · producer: " + meta.producer_dir + " · paper: " + meta.paper_dir) : "no artifact bundle loaded"}>
      <Dot tone={dot} />
      <span>{label}</span>
    </div>
  );
}

// Banner used by pages that intentionally stay on design/demo data.
function DemoDataBanner({ children }) {
  const live = usePhxLive();
  if (!live) return null;
  return <div className="phx-banner">{children}</div>;
}

// Copy-CA chip. Shows next to shortened mints everywhere; copies the FULL
// mint/CA exactly (no prefix, no ellipsis). Renders nothing when no full
// value is available. stopPropagation so row-click drawers don't open.
function phxCopyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text);
  }
  return new Promise((resolve, reject) => {
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      ok ? resolve() : reject(new Error("execCommand failed"));
    } catch (e) { reject(e); }
  });
}

function CopyCA({ value, label }) {
  const [state, setState] = React.useState("idle"); // idle | copied | failed
  if (!value) return null;
  const onClick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    phxCopyText(String(value)).then(
      () => setState("copied"),
      () => setState("failed"),
    );
    setTimeout(() => setState("idle"), 1400);
  };
  return (
    <button
      type="button"
      className={"ca-copy" + (state === "copied" ? " copied" : "")}
      title={String(value)}
      onClick={onClick}
    >
      {state === "copied" ? "Copied" : state === "failed" ? "Select in drawer" : (label || "Copy CA")}
    </button>
  );
}

// Full-CA line for drawers: selectable monospace full value + copy chip.
function FullCA({ value }) {
  if (!value) return null;
  return (
    <div className="cd-addr mono cd-addr-full">
      {value} <CopyCA value={value} />
    </div>
  );
}

Object.assign(window, {
  usePhxData, usePhxLive, usePhxMeta, DataSourceBadge, DemoDataBanner,
  CopyCA, FullCA, PhxStore,
});
