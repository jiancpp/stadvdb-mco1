"use client";

import { useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Filters, SlowResponse, money0, useApi } from "@/lib/api";
import { Card, CardHead, ErrorNote, Toggle } from "../ui";

type Mode = "hour" | "period";
const GOLD = "#f5b301";
const RED = "#e11d2e";

function SlowLabel({ viewBox, l1, l2 }: { viewBox?: { x: number; y: number; width: number }; l1: string; l2: string }) {
  if (!viewBox) return null;
  const w = 152;
  const x = viewBox.x + viewBox.width / 2 - w / 2;
  const y = viewBox.y + 8;
  return (
    <g>
      <rect x={x} y={y} width={w} height={38} rx={8} fill="#fff" stroke="#f3e2b3" />
      <text x={x + w / 2} y={y + 16} textAnchor="middle" fontSize={12} fontWeight={700} fill="#111827">{l1}</text>
      <text x={x + w / 2} y={y + 31} textAnchor="middle" fontSize={12} fontWeight={600} fill="#111827">{l2}</text>
    </g>
  );
}

export default function SlowWindows({ filters }: { filters: Filters }) {
  const [mode, setMode] = useState<Mode>("hour");
  const { data, loading, error } = useApi<SlowResponse>("slow-windows", filters, { mode });
  const sw = data?.slow_window;

  return (
    <Card loading={loading}>
      <CardHead
        title="Slow windows: speed vs. yield"
        sub={<>Your best when traffic slows.{data?.yield_ratio ? <> Plan for up to {data.yield_ratio.toFixed(1)} × yield.</> : null}</>}
        right={<Toggle<Mode> options={[{ value: "hour", label: "Hour" }, { value: "period", label: "Period" }]} value={mode} onChange={setMode} />}
      />
      <ErrorNote message={error} />
      <div className="line-legend">
        <span><i style={{ background: GOLD }} />Revenue per occupied hour ($)</span>
        <span><i style={{ background: RED }} />Average speed (mph)</span>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={data?.points ?? []} margin={{ top: 8, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#eef0f3" />
          {sw && (
            <ReferenceArea yAxisId="rev" x1={sw.from} x2={sw.to} fill="#fde7b0" fillOpacity={0.55} stroke="none"
              label={<SlowLabel l1={`Slow window: ${sw.avg_mph.toFixed(1)} mph,`} l2={`${money0(sw.rev_per_hour)} per hour`} />} />
          )}
          <XAxis dataKey="label" tickLine={false} axisLine={false} interval={mode === "hour" ? 2 : 0} />
          <YAxis yAxisId="rev" tickLine={false} axisLine={false} width={48}
            domain={[(m: number) => Math.floor(m / 10) * 10 - 10, (m: number) => Math.ceil(m / 10) * 10 + 10]}
            tickFormatter={(v: number) => `$ ${Math.round(v)}`} />
          <YAxis yAxisId="mph" orientation="right" tickLine={false} axisLine={false} width={32}
            domain={[(m: number) => Math.floor(m) - 2, (m: number) => Math.ceil(m) + 2]} />
          <Tooltip formatter={(v: number, k: string) => (k === "avg_mph" ? [`${v.toFixed(1)} mph`, "Speed"] : [money0(v), "Revenue / occupied hr"])} />
          <Line yAxisId="rev" dataKey="rev_per_hour" stroke={GOLD} strokeWidth={2.5} dot={false} type="monotone" isAnimationActive={false} />
          <Line yAxisId="mph" dataKey="avg_mph" stroke={RED} strokeWidth={2.5} dot={false} type="monotone" isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </Card>
  );
}
