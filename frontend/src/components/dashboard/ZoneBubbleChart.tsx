"use client";

import { useMemo, useRef, useState } from "react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, XAxis, YAxis } from "recharts";
import { Filters, ZonePoint, ZoneResponse, compact, money0, useApi } from "@/lib/api";
import { Card, CardHead, ErrorNote, Toggle, heat } from "../ui";

const X_LIM = 40;
const PX_PER_DOLLAR = 6; // vertical stretch: bigger = more spread out (and more scrolling)
const VIEWPORT_H = 420; // visible height of the scroll area
const MIN_POINTS_FOR_FILTER = 12; // don't filter tiny datasets (e.g. boroughs)

type Level = "zone" | "borough";
type Outliers = "hide" | "show";
type Pt = ZonePoint & { x: number; y: number; r: number; color: string };
type Hover = { pt: Pt; left: number; top: number } | null;

/** Tukey fences on revenue/hour. k=3 only removes the truly extreme values. */
function fences(values: number[], k = 3): [number, number] {
  const s = [...values].sort((a, b) => a - b);
  const q = (p: number) => {
    const i = (s.length - 1) * p;
    const lo = Math.floor(i);
    const hi = Math.ceil(i);
    return s[lo] + (s[hi] - s[lo]) * (i - lo);
  };
  const q1 = q(0.25);
  const q3 = q(0.75);
  const iqr = q3 - q1;
  return [q1 - k * iqr, q3 + k * iqr];
}

function Bubble({
  cx = 0,
  cy = 0,
  payload,
  onHover,
}: {
  cx?: number;
  cy?: number;
  payload?: Pt;
  onHover: (pt: Pt | null, e?: React.MouseEvent) => void;
}) {
  if (!payload) return null;
  const { r, color, labeled, name, y, x } = payload;
  const short = name.length > 22 ? `${name.slice(0, 21)}…` : name;
  const w = Math.max(74, short.length * 6.3 + 18);
  const dx = x > 12 ? -(w + r + 6) : r + 6; // flip label to the left near the right edge
  return (
    <g>
      <circle
        cx={cx}
        cy={cy}
        r={r}
        fill={color}
        fillOpacity={labeled ? 0.95 : 0.6}
        stroke="#fff"
        strokeWidth={labeled ? 1.5 : 0.75}
        style={{ cursor: "pointer" }}
        onMouseEnter={(e) => onHover(payload, e)}
        onMouseMove={(e) => onHover(payload, e)}
        onMouseLeave={() => onHover(null)}
      />
      {labeled && (
        <g transform={`translate(${cx + dx},${cy - 17})`} pointerEvents="none">
          <rect width={w} height={34} rx={8} fill="#fff" fillOpacity={0.96} stroke="rgba(15,23,42,.08)" />
          <text x={9} y={14} fontSize={11} fontWeight={500} fill="#374151">{short}</text>
          <text x={9} y={28} fontSize={12} fontWeight={700} fill="#111827">{money0(y)}</text>
        </g>
      )}
    </g>
  );
}

export default function ZoneBubbleChart({ filters }: { filters: Filters }) {
  const [level, setLevel] = useState<Level>("zone");
  const [outliers, setOutliers] = useState<Outliers>("hide");
  const [hover, setHover] = useState<Hover>(null);
  const [minRev, setMinRev] = useState(0); // slider: only show zones earning at least this much per hour
  const wrapRef = useRef<HTMLDivElement>(null);

  const { data, loading, error } = useApi<ZoneResponse>("zones", filters, { level });
  const raw = data?.points ?? [];

  const { kept, hiddenCount } = useMemo(() => {
    if (outliers === "show" || raw.length < MIN_POINTS_FOR_FILTER) {
      return { kept: raw, hiddenCount: 0 };
    }
    const [lo, hi] = fences(raw.map((p) => p.rev_per_hour));
    // Drop extreme revenue values and anything off the X range (instead of piling it on the edge)
    const ok = raw.filter(
      (p) => p.rev_per_hour >= lo && p.rev_per_hour <= hi && Math.abs(p.net_flow_pct) <= X_LIM
    );
    return { kept: ok, hiddenCount: raw.length - ok.length };
  }, [raw, outliers]);

  const { pts, yMin, yMax, yTicks, rOf, maxTrips, sliderMin, sliderMax, threshold } = useMemo(() => {
    const maxTrips = Math.max(1, ...kept.map((p) => p.trips));
    const rOf = (t: number) => 4 + 16 * Math.sqrt(t / maxTrips); // smaller bubbles = less overlap

    const ys = kept.map((p) => p.rev_per_hour);
    const lo = ys.length ? Math.min(...ys) : 40;
    const hi = ys.length ? Math.max(...ys) : 120;

    // Slider runs from the lowest to the highest revenue/hour in the (outlier-filtered) data.
    // The Y domain below is NOT affected by the slider, so bubbles don't jump around while dragging.
    const sliderMin = Math.floor(lo);
    const sliderMax = Math.max(sliderMin, Math.floor(hi));
    const threshold = Math.min(Math.max(minRev, sliderMin), sliderMax);
    // Tight domain around the real data, padded a little and snapped to $10
    const yMin = Math.max(0, Math.floor((lo - 10) / 10) * 10);
    const yMax = Math.ceil((hi + 10) / 10) * 10;
    const span = Math.max(1, yMax - yMin);

    const step = span <= 100 ? 10 : 20;
    const yTicks = Array.from({ length: Math.floor(span / step) + 1 }, (_, i) => yMin + i * step);

    const pts: Pt[] = kept
      .filter((p) => p.rev_per_hour >= threshold)
      .map((p) => ({
        ...p,
        x: Math.max(-X_LIM, Math.min(X_LIM, p.net_flow_pct)),
        y: p.rev_per_hour,
        r: rOf(p.trips),
        color: heat((p.rev_per_hour - yMin) / span),
      }))
      // Draw big bubbles first so small ones stay visible (and hoverable) on top
      .sort((a, b) => b.trips - a.trips);

    return { pts, yMin, yMax, yTicks, rOf, maxTrips, sliderMin, sliderMax, threshold };
  }, [kept, minRev]);

  const chartHeight = Math.max(VIEWPORT_H, (yMax - yMin) * PX_PER_DOLLAR + 60);
  const legendTrips = [maxTrips / 100, maxTrips / 10, maxTrips / 3, maxTrips];
  const avg = data?.avg_rev_per_hour;

  const handleHover = (pt: Pt | null, e?: React.MouseEvent) => {
    if (!pt || !e || !wrapRef.current) return setHover(null);
    const box = wrapRef.current.getBoundingClientRect();
    setHover({ pt, left: e.clientX - box.left, top: e.clientY - box.top });
  };

  return (
    <Card loading={loading}>
      <CardHead
        title="Where to be: pay vs. wait"
        sub={
          <>
            Each bubble is a pickup area. Up pays more per hour. Left means cabs leave quickly<br />
            (net flow = dropoffs minus pickups).
            {hiddenCount > 0 && <> {hiddenCount} outlier{hiddenCount > 1 ? "s" : ""} hidden.</>}
          </>
        }
        right={
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", justifyContent: "flex-end" }}>
            <Toggle<Outliers>
              options={[{ value: "hide", label: "Hide outliers" }, { value: "show", label: "Show all" }]}
              value={outliers}
              onChange={(v) => { setOutliers(v); setMinRev(0); }}
            />
            <Toggle<Level>
              options={[{ value: "zone", label: "Zones" }, { value: "borough", label: "Boroughs" }]}
              value={level}
              onChange={(v) => { setLevel(v); setMinRev(0); }}
            />
          </div>
        }
      />
      <ErrorNote message={error} />

      {sliderMax > sliderMin && (
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", margin: "4px 0 10px" }}>
          <label htmlFor="min-rev" style={{ fontSize: 12, color: "#374151", whiteSpace: "nowrap" }}>
            Show zones earning at least <b>{money0(threshold)}</b>/hr
          </label>
          <span style={{ fontSize: 11, color: "#6b7280" }}>{money0(sliderMin)}</span>
          <input
            id="min-rev"
            type="range"
            min={sliderMin}
            max={sliderMax}
            step={1}
            value={threshold}
            onChange={(e) => setMinRev(Number(e.target.value))}
            style={{ flex: "1 1 180px", maxWidth: 360, accentColor: "#f59e0b", border: "none" }}
          />
          <span style={{ fontSize: 11, color: "#6b7280" }}>{money0(sliderMax)}</span>
          <span style={{ fontSize: 12, color: "#6b7280", whiteSpace: "nowrap" }}>
            {pts.length} of {kept.length} shown
          </span>
          {threshold > sliderMin && (
            <button
              type="button"
              onClick={() => setMinRev(0)}
              style={{ fontSize: 12, border: "none", background: "none", color: "#2563eb", cursor: "pointer", padding: 0 }}
            >
              Reset
            </button>
          )}
        </div>
      )}

      <div className="bubble-wrap" ref={wrapRef} style={{ position: "relative" }}>
        <span className="quad tl">High pay,<br />short wait.<br /><b>Best opportunities.</b></span>
        <span className="quad tr">High pay,<br />long wait.<br /><b>Slower outflow.</b></span>
        <span className="quad bl">Lower pay,<br />short wait.<br /><b>Quick turnover.</b></span>
        <span className="quad br">Lower pay,<br />long wait.<br /><b>Avoid or limit.</b></span>

        {/* Vertical scroll area: the chart is taller than the viewport so bubbles spread out */}
        <div style={{ maxHeight: VIEWPORT_H, overflowY: "auto", overflowX: "hidden" }}>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <ScatterChart margin={{ top: 16, right: 24, bottom: 28, left: 8 }}>
              <CartesianGrid stroke="#eef0f3" />
              <XAxis
                type="number"
                dataKey="x"
                domain={[-X_LIM, X_LIM]}
                ticks={[-40, -20, 0, 20, 40]}
                allowDataOverflow
                tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`}
                tickLine={false}
                axisLine={false}
                label={{ value: "Net flow (% of pickups)", position: "bottom", offset: 6, fontSize: 12 }}
              />
              <YAxis
                type="number"
                dataKey="y"
                domain={[yMin, yMax]}
                ticks={yTicks}
                tickFormatter={(v: number) => `$${v}`}
                tickLine={false}
                axisLine={false}
                label={{ value: "Revenue per occupied hour", angle: -90, position: "insideLeft", offset: 0, fontSize: 12 }}
              />
              {avg != null && avg >= yMin && avg <= yMax && (
                <ReferenceLine y={avg} stroke="#94a3b8" strokeDasharray="4 4" />
              )}
              {/* No recharts <Tooltip>: the tooltip below only shows while hovering a bubble */}
              <Scatter
                data={pts}
                isAnimationActive={false}
                shape={(p: { cx?: number; cy?: number; payload?: Pt }) => <Bubble {...p} onHover={handleHover} />}
              />
            </ScatterChart>
          </ResponsiveContainer>
        </div>

        {hover && (
          <div
            className="tip"
            style={{
              position: "absolute",
              left: Math.min(hover.left + 14, (wrapRef.current?.clientWidth ?? 0) - 200),
              top: Math.max(0, hover.top - 10),
              pointerEvents: "none",
              zIndex: 20,
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            <b>{hover.pt.name}</b>
            <span>{hover.pt.borough}</span>
            <span>{money0(hover.pt.rev_per_hour)} per occupied hour</span>
            <span>
              Net flow {hover.pt.net_flow_pct >= 0 ? "+" : ""}
              {hover.pt.net_flow_pct.toFixed(1)}% of pickups
            </span>
            <span>{compact(hover.pt.trips)} trips</span>
          </div>
        )}
      </div>

      <div className="bubble-legend">
        <div>
          <small>Revenue per hour</small>
          <div className="grad-bar" />
          <div className="grad-ends"><span>${yMin}</span><span>${yMax}</span></div>
        </div>
        <div className="size-legend">
          <small>Bubble size = Number of trips</small>
          <div>
            {legendTrips.map((t, i) => (
              <span key={i}>
                <i style={{ width: rOf(t) * 2, height: rOf(t) * 2 }} />
                {compact(t)}{i === 3 ? "+" : ""}
              </span>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}