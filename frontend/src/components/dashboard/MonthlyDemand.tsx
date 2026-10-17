"use client";

import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, ResponsiveContainer, XAxis, YAxis, type LabelProps } from "recharts";
import { DemandResponse, Filters, compact, signedPct, useApi } from "@/lib/api";
import { Card, CardHead, ErrorNote, heat } from "../ui";

const barColor = (p: number) => (p < 0 ? (p < -8 ? "#fdebc0" : "#fcdc9f") : heat(0.45 + 0.55 * Math.min(1, p / 8)));

function PctLabel({ x, y, width, height, value }: LabelProps) {
  const v = Number(value);
  const top = Math.min(Number(y), Number(y) + Number(height));
  const bottom = Math.max(Number(y), Number(y) + Number(height));
  return (
    <text x={Number(x) + Number(width) / 2} y={v >= 0 ? top - 6 : bottom + 15} textAnchor="middle" fontSize={12} fontWeight={700} fill="#1f2937">
      {signedPct(v)}
    </text>
  );
}

export default function MonthlyDemand({ filters }: { filters: Filters }) {
  const { data, loading, error } = useApi<DemandResponse>("monthly-demand", filters);
  const months = (data?.months ?? []).map((m) => ({ ...m, pct: m.pct_vs_avg ?? 0 }));
  const lim = Math.max(10, Math.ceil(Math.max(0, ...months.map((m) => Math.abs(m.pct))) / 5) * 5);

  return (
    <Card loading={loading}>
      <CardHead
        title="Monthly rides demand vs. normal"
        sub={`Trips per day by month against the yearly average of ${data?.avg_trips_per_day ? compact(data.avg_trips_per_day).toLowerCase() : "—"}. Add cars in red months, and scale in pale ones.`}
      />
      <ErrorNote message={error} />
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={months} margin={{ top: 26, right: 8, left: 0, bottom: 0 }} barCategoryGap="14%">
          <CartesianGrid vertical={false} stroke="#eef0f3" />
          <ReferenceLine y={0} stroke="#cbd5e1" />
          <XAxis dataKey="month" tickLine={false} axisLine={false} />
          <YAxis domain={[-lim, lim]} ticks={[-lim, 0, lim]} tickLine={false} axisLine={false} width={44}
            tickFormatter={(v: number) => `${v > 0 ? "+" : ""}${v}%`} />
          <Bar dataKey="pct" radius={[4, 4, 4, 4]} isAnimationActive={false}>
            {months.map((m) => <Cell key={`${m.year}-${m.month}`} fill={barColor(m.pct)} />)}
            <LabelList dataKey="pct" content={PctLabel} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  );
}
