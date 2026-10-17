"use client";

import { useState } from "react";
import { CartesianGrid, ReferenceLine, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis } from "recharts";
import { Filters, ZonePoint, ZoneResponse, compact, money0, useApi } from "@/lib/api";
import { Card, CardHead, ErrorNote, Toggle, heat } from "../ui";

const X_LIM = 40;
type Level = "zone" | "borough";
type Pt = ZonePoint & { x: number; y: number; r: number; color: string };

function Bubble({ cx = 0, cy = 0, payload }: { cx?: number; cy?: number; payload?: Pt }) {
  if (!payload) return null;
  const { r, color, labeled, name, y, x } = payload;
  const short = name.length > 22 ? `${name.slice(0, 21)}…` : name;
  const w = Math.max(74, short.length * 6.3 + 18);
  const dx = x > 12 ? -(w + r + 6) : r + 6; // flip label to the left near the right edge
  return (
    <g>
      <circle cx={cx} cy={cy} r={r} fill={color} fillOpacity={labeled ? 0.95 : 0.5} stroke="#fff" strokeWidth={labeled ? 1.5 : 0.5} />
      {labeled && (
        <g transform={`translate(${cx + dx},${cy - 17})`}>
          <rect width={w} height={34} rx={8} fill="#fff" fillOpacity={0.96} stroke="rgba(15,23,42,.08)" />
          <text x={9} y={14} fontSize={11} fontWeight={500} fill="#374151">{short}</text>
          <text x={9} y={28} fontSize={12} fontWeight={700} fill="#111827">{money0(y)}</text>
        </g>
      )}
    </g>
  );
}

function Tip({ active, payload }: { active?: boolean; payload?: { payload: Pt }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="tip">
      <b>{p.name}</b>
      <span>{p.borough}</span>
      <span>{money0(p.rev_per_hour)} per occupied hour</span>
      <span>Net flow {p.net_flow_pct >= 0 ? "+" : ""}{p.net_flow_pct.toFixed(1)}% of pickups</span>
      <span>{compact(p.trips)} trips</span>
    </div>
  );
}

export default function ZoneBubbleChart({ filters }: { filters: Filters }) {
  const [level, setLevel] = useState<Level>("zone");
  const { data, loading, error } = useApi<ZoneResponse>("zones", filters, { level });
  const raw = data?.points ?? [];

  const maxTrips = Math.max(1, ...raw.map((p) => p.trips));
  const rOf = (t: number) => 5 + 24 * Math.sqrt(t / maxTrips);
  const ys = raw.map((p) => p.rev_per_hour);
  const yMin = Math.floor(Math.min(...ys, 40) / 20) * 20;
  const yMax = Math.ceil(Math.max(...ys, 120) / 20) * 20;
  const pts: Pt[] = raw.map((p) => ({
    ...p,
    x: Math.max(-X_LIM, Math.min(X_LIM, p.net_flow_pct)),
    y: p.rev_per_hour,
    r: rOf(p.trips),
    color: heat((p.rev_per_hour - yMin) / (yMax - yMin)),
  }));
  const legendTrips = [maxTrips / 100, maxTrips / 10, maxTrips / 3, maxTrips];

  return (
    <Card loading={loading}>
      <CardHead
        title="Where to be: pay vs. wait"
        sub={<>Each bubble is a pickup area. Up pays more per hour. Left means cabs leave quickly<br />(net flow = dropoffs minus pickups).</>}
        right={<Toggle<Level> options={[{ value: "zone", label: "Zones" }, { value: "borough", label: "Boroughs" }]} value={level} onChange={setLevel} />}
      />
      <ErrorNote message={error} />
      <div className="bubble-wrap">
        <span className="quad tl">High pay,<br />short wait.<br /><b>Best opportunities.</b></span>
        <span className="quad tr">High pay,<br />long wait.<br /><b>Slower outflow.</b></span>
        <span className="quad bl">Lower pay,<br />short wait.<br /><b>Quick turnover.</b></span>
        <span className="quad br">Lower pay,<br />long wait.<br /><b>Avoid or limit.</b></span>
        <ResponsiveContainer width="100%" height={380}>
          <ScatterChart margin={{ top: 10, right: 24, bottom: 28, left: 8 }}>
            <CartesianGrid stroke="#eef0f3" />
            <XAxis type="number" dataKey="x" domain={[-X_LIM, X_LIM]} ticks={[-40, -20, 0, 20, 40]} allowDataOverflow
              tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`} tickLine={false} axisLine={false}
              label={{ value: "Net flow (% of pickups)", position: "bottom", offset: 6, fontSize: 12 }} />
            <YAxis type="number" dataKey="y" domain={[yMin, yMax]} ticks={Array.from({ length: (yMax - yMin) / 20 + 1 }, (_, i) => yMin + i * 20)}
              tickFormatter={(v: number) => `$${v}`} tickLine={false} axisLine={false}
              label={{ value: "Revenue per occupied hour", angle: -90, position: "insideLeft", offset: 0, fontSize: 12 }} />
            <ReferenceLine x={0} stroke="#cbd5e1" />
            {data?.avg_rev_per_hour != null && <ReferenceLine y={data.avg_rev_per_hour} stroke="#94a3b8" strokeDasharray="4 4" />}
            <Tooltip content={<Tip />} cursor={false} />
            <Scatter data={pts} shape={(p: { cx?: number; cy?: number; payload?: Pt }) => <Bubble {...p} />} isAnimationActive={false} />
          </ScatterChart>
        </ResponsiveContainer>
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
