// Phoenix — PriceCurveEvidenceCard
// Reusable price-curve evidence component. Used across Live, Candidates, Decisions,
// Outcomes, Calibration, and Research. Mock-only data. No real chart API.
//
// Modes:
//   "mini"      — sparkline only (in-table, ~120×28). No labels.
//   "candidate" — small evidence card showing ATH + current + distance to tier.
//   "decision"  — point-in-time view. ATH + decision + drawdown. Future action de-emphasized.
//   "outcome"   — full proof curve. Decision + bounce + drawdown + reclaim + window.
//   "evidence"  — labeling-focused. All markers + note line.
//   "archetype" — research example. Decision + outcome + caption.

function PriceCurve({
  data, mode = "outcome", height = 180, width = null,
  caption = null, note = null, censored = false,
}) {
  if (!data || !data.points || !data.points.length) {
    return <div className="pc-empty">no curve data</div>;
  }

  const isMini = mode === "mini";
  const W = width || (isMini ? 120 : 560);
  const H = height || (isMini ? 28 : 180);
  const padL = isMini ? 2 : 30;
  const padR = isMini ? 2 : 20;
  const padT = isMini ? 2 : 18;
  const padB = isMini ? 2 : 22;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const pts = data.points;
  const minP = Math.min(...pts.map((p) => p.p));
  const maxP = Math.max(...pts.map((p) => p.p));
  const pSpan = Math.max(maxP - minP, 0.001);

  // Coords: t∈[0,1] → x; p∈[minP,maxP] → y (inverted)
  const x = (t) => padL + t * plotW;
  const y = (p) => padT + (1 - (p - minP) / pSpan) * plotH;

  // Smoothed path
  const path = (() => {
    let d = `M ${x(pts[0].t).toFixed(2)} ${y(pts[0].p).toFixed(2)}`;
    for (let i = 1; i < pts.length; i++) {
      const p0 = pts[i - 1], p1 = pts[i];
      const cx0 = x(p0.t) + (x(p1.t) - x(p0.t)) * 0.5;
      const cx1 = x(p0.t) + (x(p1.t) - x(p0.t)) * 0.5;
      d += ` C ${cx0.toFixed(2)} ${y(p0.p).toFixed(2)}, ${cx1.toFixed(2)} ${y(p1.p).toFixed(2)}, ${x(p1.t).toFixed(2)} ${y(p1.p).toFixed(2)}`;
    }
    return d;
  })();

  // Area fill path (close to bottom)
  const areaPath = path + ` L ${x(pts[pts.length - 1].t).toFixed(2)} ${(padT + plotH).toFixed(2)} L ${x(pts[0].t).toFixed(2)} ${(padT + plotH).toFixed(2)} Z`;

  const m = data.markers;

  // Decide which markers to show per mode
  const show = {
    firstSeen: ["evidence", "outcome", "archetype"].includes(mode),
    migration: ["evidence"].includes(mode),
    ath: ["candidate", "decision", "outcome", "evidence", "archetype"].includes(mode),
    decision: !isMini && ["decision", "outcome", "evidence", "archetype", "candidate"].includes(mode) && m.decision,
    outcomeWindow: ["outcome", "evidence", "archetype"].includes(mode) && m.outcomeStart,
    maxBounce: ["outcome", "evidence", "archetype"].includes(mode) && m.maxBounce,
    maxDrawdown: ["outcome", "evidence"].includes(mode) && m.maxDrawdown,
    current: !["decision"].includes(mode), // hide future-current in Decisions mode
    tierLine: ["candidate", "decision", "outcome", "evidence"].includes(mode) && m.tier,
    stale: m.stale && ["evidence", "outcome", "decision"].includes(mode),
    futureMask: mode === "decision" && m.decision, // mask post-decision portion
  };

  const fmtPct = (a, b) => ((a / b - 1) * 100).toFixed(1) + "%";

  return (
    <div className={"pc-wrap pc-" + mode + (censored ? " pc-censored" : "")}>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} preserveAspectRatio="none" className="pc-svg">
        <defs>
          <linearGradient id={"pc-grad-" + mode} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="rgba(255,140,40,0.35)" />
            <stop offset="100%" stopColor="rgba(255,140,40,0)" />
          </linearGradient>
          <linearGradient id={"pc-stroke-" + mode} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="#ff6a1f" />
            <stop offset="100%" stopColor="#ffd07a" />
          </linearGradient>
          <pattern id="pc-stale-pat" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
            <rect width="6" height="6" fill="rgba(255,180,70,0.06)" />
            <line x1="0" y1="0" x2="0" y2="6" stroke="rgba(255,180,70,0.30)" strokeWidth="1" />
          </pattern>
        </defs>

        {/* Gridlines (skip for mini) */}
        {!isMini && (
          <g className="pc-grid">
            {[0.25, 0.5, 0.75].map((g, i) => (
              <line key={i}
                x1={padL} x2={W - padR}
                y1={padT + g * plotH} y2={padT + g * plotH}
                stroke="rgba(255,255,255,0.04)" strokeDasharray="2 4" />
            ))}
          </g>
        )}

        {/* Outcome window shading */}
        {show.outcomeWindow && (
          <rect
            x={x(m.outcomeStart.t)}
            y={padT}
            width={Math.max(2, x(m.outcomeEnd ? m.outcomeEnd.t : 1) - x(m.outcomeStart.t))}
            height={plotH}
            fill="rgba(255,140,40,0.05)"
            stroke="rgba(255,140,60,0.18)"
            strokeDasharray="2 3"
          />
        )}

        {/* Stale region */}
        {show.stale && (
          <rect
            x={x(m.stale.from)} y={padT}
            width={x(m.stale.to) - x(m.stale.from)} height={plotH}
            fill="url(#pc-stale-pat)"
            stroke="rgba(255,180,70,0.30)" strokeDasharray="2 2"
          />
        )}

        {/* Area fill */}
        <path d={areaPath} fill={`url(#pc-grad-${mode})`} />

        {/* Future mask for Decisions mode */}
        {show.futureMask && (
          <rect
            x={x(m.decision.t)} y={padT}
            width={W - padR - x(m.decision.t)} height={plotH}
            fill="rgba(8,7,10,0.65)"
          />
        )}

        {/* Curve stroke */}
        <path d={path} fill="none" stroke={`url(#pc-stroke-${mode})`} strokeWidth={isMini ? 1.3 : 1.8} strokeLinejoin="round" strokeLinecap="round" />

        {/* ATH horizontal reference */}
        {show.ath && !isMini && (
          <g>
            <line x1={padL} x2={W - padR} y1={y(m.ath.p)} y2={y(m.ath.p)}
              stroke="rgba(255,200,120,0.30)" strokeDasharray="3 3" />
            <text x={W - padR - 2} y={y(m.ath.p) - 4} textAnchor="end"
              className="pc-label pc-label-ath">ATH</text>
          </g>
        )}

        {/* Tier line (e.g. -60% from ATH) */}
        {show.tierLine && !isMini && (() => {
          const tierP = m.ath.p * (m.tier === "T1" ? 0.40 : m.tier === "T2" ? 0.50 : 0.55);
          if (tierP < minP || tierP > maxP) return null;
          return (
            <g>
              <line x1={padL} x2={W - padR} y1={y(tierP)} y2={y(tierP)}
                stroke="rgba(255,80,60,0.25)" strokeDasharray="2 4" />
              <text x={padL + 4} y={y(tierP) - 4}
                className="pc-label pc-label-tier">{m.tier} threshold</text>
            </g>
          );
        })()}

        {/* Decision vertical */}
        {show.decision && (
          <g>
            <line x1={x(m.decision.t)} x2={x(m.decision.t)} y1={padT} y2={padT + plotH}
              stroke="rgba(255,140,60,0.55)" strokeWidth="1" strokeDasharray="3 2" />
            <circle cx={x(m.decision.t)} cy={y(m.decision.p)} r="4"
              fill="#ff8a2a" stroke="#0c0a0f" strokeWidth="2" />
            <text x={x(m.decision.t) + 6} y={padT + 12}
              className="pc-label pc-label-decision">decision</text>
          </g>
        )}

        {/* First seen */}
        {show.firstSeen && !isMini && (
          <g>
            <circle cx={x(m.firstSeen.t)} cy={y(m.firstSeen.p)} r="3"
              fill="#7e94b3" stroke="#0c0a0f" strokeWidth="1.5" />
            {mode !== "outcome" && (
              <text x={x(m.firstSeen.t) + 5} y={y(m.firstSeen.p) - 6}
                className="pc-label pc-label-faint">first seen</text>
            )}
          </g>
        )}

        {/* ATH marker */}
        {show.ath && !isMini && (
          <g>
            <circle cx={x(m.ath.t)} cy={y(m.ath.p)} r="3.5"
              fill="#ffd07a" stroke="#0c0a0f" strokeWidth="1.5" />
          </g>
        )}

        {/* Max bounce */}
        {show.maxBounce && !isMini && (
          <g>
            <circle cx={x(m.maxBounce.t)} cy={y(m.maxBounce.p)} r="4"
              fill="#7df0a4" stroke="#0c0a0f" strokeWidth="1.5" />
            <text x={x(m.maxBounce.t) + 5} y={y(m.maxBounce.p) - 5}
              className="pc-label pc-label-ok">
              +{((m.maxBounce.p / (m.decision ? m.decision.p : m.firstSeen.p) - 1) * 100).toFixed(0)}%
            </text>
          </g>
        )}

        {/* Max drawdown after decision */}
        {show.maxDrawdown && !isMini && m.decision && (
          <g>
            <circle cx={x(m.maxDrawdown.t)} cy={y(m.maxDrawdown.p)} r="3.5"
              fill="#ff8a7a" stroke="#0c0a0f" strokeWidth="1.5" />
          </g>
        )}

        {/* Current */}
        {show.current && (
          <g>
            <circle cx={x(m.current.t)} cy={y(m.current.p)} r={isMini ? 2 : 4}
              fill="#ffd07a" stroke="#0c0a0f" strokeWidth={isMini ? 1 : 2}>
              {!isMini && (
                <animate attributeName="r" values="4;5.5;4" dur="2.4s" repeatCount="indefinite" />
              )}
            </circle>
            {!isMini && mode !== "decision" && (
              <text x={x(m.current.t) - 6} y={y(m.current.p) - 8} textAnchor="end"
                className="pc-label pc-label-current">current</text>
            )}
          </g>
        )}

        {/* ATH reclaim badge */}
        {m.athReclaim && !isMini && (
          <g>
            <text x={W - padR - 4} y={padT + 10} textAnchor="end"
              className="pc-label pc-label-reclaim">★ reclaimed ATH</text>
          </g>
        )}
      </svg>

      {/* Footer (not in mini) */}
      {!isMini && (caption || note || mode === "candidate") && (
        <div className="pc-foot">
          {caption && <div className="pc-caption">{caption}</div>}
          {note && <div className="pc-note">{note}</div>}
        </div>
      )}

      {censored && !isMini && (
        <div className="pc-censored-banner">
          <span>⚠</span>
          <span>Curve censored — measurement unreliable. Result not counted.</span>
        </div>
      )}
    </div>
  );
}

// Convenience wrapper: feed a token (id + outcome/stage hints), get the card.
function PriceCurveEvidenceCard({ token, mode = "outcome", height, width, caption, note }) {
  const data = window.getCurveData({
    id: token.id || token.token,
    outcome: token.outcome || token.status,
    decision: token.decision,
    stage: token.stage,
  });
  const censored = ["CENSORED", "NO_DATA"].includes(token.outcome || token.status);
  return (
    <PriceCurve
      data={data}
      mode={mode}
      height={height}
      width={width}
      caption={caption}
      note={note}
      censored={censored}
    />
  );
}

window.PriceCurve = PriceCurve;
window.PriceCurveEvidenceCard = PriceCurveEvidenceCard;
