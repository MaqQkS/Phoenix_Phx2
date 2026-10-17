// Phoenix — synthetic curve data per token
// Each token gets a price series + event markers based on its outcome archetype.
// All data is mock — no real chart API.

// Generate a smoothed series following an archetype.
// Returns array of { t, p } where t is 0..1 along the timeline and p is price.
function genCurve(archetype, seed = 1) {
  // Tiny PRNG for reproducibility
  let s = seed * 9301 + 49297;
  const rnd = () => {
    s = (s * 9301 + 49297) % 233280;
    return s / 233280;
  };

  const N = 60;
  const pts = [];
  const launch = 1.0;

  // Archetype scripts: a sequence of (t, p) anchors. We interpolate smoothly between them.
  const scripts = {
    HIT: [
      [0.00, 1.00], [0.08, 1.20], [0.18, 1.85], [0.28, 3.40],
      [0.36, 4.80], [0.42, 4.20],   // ATH around 0.36
      [0.55, 2.10], [0.62, 1.92],   // T1 drawdown valley = decision
      [0.78, 3.20], [0.92, 3.50],   // bounce
    ],
    RECLAIMED_ATH: [
      [0.00, 1.00], [0.10, 1.40], [0.22, 2.60], [0.32, 4.10],
      [0.42, 5.20], [0.48, 4.60],   // first ATH
      [0.58, 2.20], [0.65, 2.00],   // decision (T1 drawdown)
      [0.80, 4.30], [0.90, 5.50], [0.98, 5.80], // reclaimed
    ],
    MISS: [
      [0.00, 1.00], [0.10, 1.30], [0.22, 2.20], [0.32, 3.40],
      [0.40, 4.20], [0.46, 3.80],
      [0.58, 1.70], [0.65, 1.55],   // decision
      [0.72, 1.74], [0.80, 1.28], [0.92, 1.30], // small bounce, then fall
    ],
    SAVED: [
      [0.00, 1.00], [0.08, 1.25], [0.18, 2.10], [0.28, 3.20],
      [0.36, 3.60], [0.42, 3.10],
      [0.52, 2.00], [0.58, 1.45],   // decision (skip)
      [0.70, 1.05], [0.82, 0.62], [0.94, 0.42], // continued fall
    ],
    DEAD: [
      [0.00, 1.00], [0.10, 2.40], [0.20, 4.20],
      [0.28, 4.80], [0.34, 3.10],
      [0.42, 0.95],                 // decision (already in collapse)
      [0.55, 0.42], [0.70, 0.22], [0.85, 0.08], [0.95, 0.04],
    ],
    MISSED_RUNNER: [
      [0.00, 1.00], [0.10, 1.20], [0.20, 1.60], [0.32, 2.10],
      [0.40, 2.20], [0.48, 1.90],
      [0.55, 1.42],                 // decision (skip below tier)
      [0.62, 1.20], [0.70, 1.60], [0.80, 3.10], [0.92, 4.30], // RAN
    ],
    PENDING: [
      [0.00, 1.00], [0.10, 1.40], [0.22, 2.20], [0.34, 3.20],
      [0.44, 3.60], [0.52, 3.00],
      [0.62, 1.85], [0.70, 1.78],   // decision recent
      [0.78, 1.92], [0.88, 1.95],   // small wobble — window still open
    ],
    CENSORED: [
      [0.00, 1.00], [0.08, 1.30], [0.20, 1.80], [0.30, 2.40],
      [0.42, 2.10], [0.55, 1.60], [0.70, 1.55], [0.85, 1.45], [0.95, 1.50],
    ],
    NO_DATA: [
      [0.00, 1.00], [0.10, 1.20], [0.22, 1.50], [0.30, 1.80],
      [0.40, 1.90],                 // last fresh
      [0.55, 1.86], [0.70, 1.84], [0.85, 1.84], [0.95, 1.84], // stale plateau
    ],
    PARTIAL: [
      [0.00, 1.00], [0.10, 1.40], [0.22, 2.10], [0.34, 2.80],
      [0.42, 3.10], [0.50, 2.50],
      [0.60, 1.20], [0.66, 1.05],
      [0.78, 1.38], [0.90, 1.32],
    ],
    LATER_ALERTED: [
      [0.00, 1.00], [0.10, 1.20], [0.22, 1.60], [0.34, 2.00],
      [0.42, 2.20], [0.50, 1.65],   // first watch
      [0.60, 1.20], [0.68, 1.08],   // crossed tier
      [0.80, 1.78], [0.92, 2.10],   // later alerted, modest bounce
    ],
    EXPIRED: [
      [0.00, 1.00], [0.10, 1.10], [0.22, 1.18], [0.34, 1.22],
      [0.46, 1.18], [0.58, 1.14], [0.70, 1.12], [0.82, 1.13], [0.94, 1.11],
    ],
    DIED: [
      [0.00, 1.00], [0.10, 1.15], [0.22, 1.30], [0.32, 1.10],
      [0.42, 0.85],                 // watch
      [0.55, 0.55], [0.70, 0.32], [0.85, 0.18], [0.94, 0.12],
    ],
    CANDIDATE_NEAR: [
      [0.00, 1.00], [0.08, 1.30], [0.20, 2.20], [0.32, 3.40],
      [0.42, 4.10], [0.50, 3.60],
      [0.65, 1.95], [0.78, 1.78], [0.90, 1.74], // approaching tier from above
    ],
  };

  const script = scripts[archetype] || scripts.PENDING;

  // Linear interpolate + slight jitter for organic feel
  for (let i = 0; i < N; i++) {
    const t = i / (N - 1);
    let p = 1.0;
    for (let j = 0; j < script.length - 1; j++) {
      const [t0, p0] = script[j];
      const [t1, p1] = script[j + 1];
      if (t >= t0 && t <= t1) {
        const k = (t - t0) / (t1 - t0);
        // ease in/out
        const e = k * k * (3 - 2 * k);
        p = p0 + (p1 - p0) * e;
        break;
      }
    }
    // jitter scaled to local price
    const jitter = (rnd() - 0.5) * 0.04 * p;
    pts.push({ t, p: Math.max(0.001, p + jitter) });
  }
  return pts;
}

// Find the indexed point closest to a target t value.
function ptAt(pts, t) {
  let best = pts[0], bestD = 1e9;
  for (const p of pts) {
    const d = Math.abs(p.t - t);
    if (d < bestD) { bestD = d; best = p; }
  }
  return best;
}

// Build the markers object based on archetype + price points.
function buildMarkers(archetype, pts, customAth) {
  const firstSeen = pts[0];
  // Find ATH (max price)
  const ath = pts.reduce((m, p) => p.p > m.p ? p : m, pts[0]);
  // Migration ~ slightly after first seen
  const migration = ptAt(pts, 0.04);
  const current = pts[pts.length - 1];

  let decision = null, outcomeStart = null, outcomeEnd = null;
  let maxBounce = null, maxDrawdown = null, athReclaim = false;
  let stale = null;
  let tier = null;

  // Decision point varies by archetype
  if (archetype === "HIT" || archetype === "RECLAIMED_ATH") {
    // Decision = trough before bounce, near 0.58–0.62
    decision = ptAt(pts, archetype === "RECLAIMED_ATH" ? 0.62 : 0.60);
    outcomeStart = decision;
    outcomeEnd = current;
    // Max bounce = peak after decision
    const after = pts.filter((p) => p.t >= decision.t);
    maxBounce = after.reduce((m, p) => p.p > m.p ? p : m, decision);
    maxDrawdown = after.reduce((m, p) => p.p < m.p ? p : m, decision);
    athReclaim = archetype === "RECLAIMED_ATH" && maxBounce.p >= ath.p * 0.98;
    tier = "T1";
  } else if (archetype === "MISS") {
    decision = ptAt(pts, 0.62);
    outcomeStart = decision;
    outcomeEnd = current;
    const after = pts.filter((p) => p.t >= decision.t);
    maxBounce = after.reduce((m, p) => p.p > m.p ? p : m, decision);
    maxDrawdown = after.reduce((m, p) => p.p < m.p ? p : m, decision);
    tier = "T2";
  } else if (archetype === "SAVED" || archetype === "DEAD") {
    decision = ptAt(pts, archetype === "DEAD" ? 0.42 : 0.55);
    outcomeStart = decision;
    outcomeEnd = current;
    const after = pts.filter((p) => p.t >= decision.t);
    maxBounce = after.reduce((m, p) => p.p > m.p ? p : m, decision);
    maxDrawdown = after.reduce((m, p) => p.p < m.p ? p : m, decision);
  } else if (archetype === "MISSED_RUNNER") {
    decision = ptAt(pts, 0.55);
    outcomeStart = decision;
    outcomeEnd = current;
    const after = pts.filter((p) => p.t >= decision.t);
    maxBounce = after.reduce((m, p) => p.p > m.p ? p : m, decision);
    maxDrawdown = after.reduce((m, p) => p.p < m.p ? p : m, decision);
  } else if (archetype === "PENDING") {
    decision = ptAt(pts, 0.66);
    outcomeStart = decision;
    outcomeEnd = null; // open
  } else if (archetype === "CENSORED" || archetype === "NO_DATA") {
    decision = ptAt(pts, 0.42);
    stale = { from: 0.42, to: 1.0 };
  } else if (archetype === "PARTIAL") {
    decision = ptAt(pts, 0.62);
    outcomeStart = decision;
    outcomeEnd = current;
    const after = pts.filter((p) => p.t >= decision.t);
    maxBounce = after.reduce((m, p) => p.p > m.p ? p : m, decision);
    maxDrawdown = after.reduce((m, p) => p.p < m.p ? p : m, decision);
  } else if (archetype === "LATER_ALERTED") {
    decision = ptAt(pts, 0.50); // WATCH point
    const alert = ptAt(pts, 0.68);
    outcomeStart = alert;
    outcomeEnd = current;
    tier = "T3";
  } else if (archetype === "EXPIRED" || archetype === "DIED") {
    decision = ptAt(pts, 0.32);
    outcomeStart = decision;
    outcomeEnd = current;
    const after = pts.filter((p) => p.t >= decision.t);
    maxBounce = after.reduce((m, p) => p.p > m.p ? p : m, decision);
    maxDrawdown = after.reduce((m, p) => p.p < m.p ? p : m, decision);
  } else if (archetype === "CANDIDATE_NEAR") {
    // No decision yet — token is in the queue
    decision = null;
  }

  return { firstSeen, migration, ath, decision, current, outcomeStart, outcomeEnd, maxBounce, maxDrawdown, athReclaim, stale, tier };
}

// Map outcome status / decision to an archetype name
function archetypeFor({ outcome, decision, stage }) {
  if (outcome === "HIT") return "HIT";
  if (outcome === "RECLAIMED_ATH") return "RECLAIMED_ATH";
  if (outcome === "MISS") return "MISS";
  if (outcome === "SAVED_BY_SKIP") return "SAVED";
  if (outcome === "DEAD") return "DEAD";
  if (outcome === "MISSED_RUNNER") return "MISSED_RUNNER";
  if (outcome === "PENDING") return "PENDING";
  if (outcome === "CENSORED") return "CENSORED";
  if (outcome === "NO_DATA") return "NO_DATA";
  if (outcome === "PARTIAL") return "PARTIAL";
  if (outcome === "LATER_ALERTED") return "LATER_ALERTED";
  if (outcome === "LATER_CANDIDATE") return "PARTIAL";
  if (outcome === "EXPIRED") return "EXPIRED";
  if (outcome === "DIED") return "DIED";
  if (stage && stage.startsWith("NEAR_")) return "CANDIDATE_NEAR";
  return "PENDING";
}

// Hash a token id to a stable seed
function seedFor(id) {
  let h = 0;
  const s = String(id || "phoenix");
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) & 0xffff;
  return h || 1;
}

// Public: get the curve data for any token by id + archetype hints
function getCurveData({ id, archetype, outcome, decision, stage }) {
  const at = archetype || archetypeFor({ outcome, decision, stage });
  const seed = seedFor(id);
  const points = genCurve(at, seed);
  const markers = buildMarkers(at, points);
  return { archetype: at, points, markers };
}

window.getCurveData = getCurveData;
