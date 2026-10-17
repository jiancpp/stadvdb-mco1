"use client";

import type { ReactNode } from "react";
import { Area, AreaChart, ResponsiveContainer, YAxis } from "recharts";

export function Card({ className = "", loading = false, children }: { className?: string; loading?: boolean; children: ReactNode }) {
  return <section className={`card ${className} ${loading ? "is-loading" : ""}`}>{children}</section>;
}

export function CardHead({ title, sub, right }: { title: string; sub?: ReactNode; right?: ReactNode }) {
  return (
    <header className="card-head">
      <div>
        <h2>{title}</h2>
        {sub && <p>{sub}</p>}
      </div>
      {right}
    </header>
  );
}

export function Toggle<T extends string>({
  options, value, onChange,
}: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="toggle" role="tablist">
      {options.map((o) => (
        <button key={o.value} role="tab" aria-selected={o.value === value} className={o.value === value ? "on" : ""} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Spark({ data, color }: { data: number[]; color: string }) {
  const rows = data.map((v, i) => ({ i, v }));
  const id = `spark${color.replace("#", "")}`;
  return (
    <ResponsiveContainer width="100%" height={56}>
      <AreaChart data={rows} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.28} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={["dataMin", "dataMax"]} />
        <Area type="monotone" dataKey="v" stroke={color} strokeWidth={2} fill={`url(#${id})`} dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function Callout({ children }: { children: ReactNode }) {
  return (
    <div className="callout">
      <span className="bulb" aria-hidden>💡</span>
      <div>{children}</div>
    </div>
  );
}

export function ErrorNote({ message }: { message: string | null }) {
  return message ? <p className="err">Could not load data: {message}. Check that the API is running and the mart views exist.</p> : null;
}

/** 0..1 -> gold -> orange -> red */
export function heat(t: number): string {
  const stops = [[251, 191, 36], [249, 115, 22], [220, 38, 38]];
  const x = Math.max(0, Math.min(1, t)) * 2;
  const i = Math.min(1, Math.floor(x));
  const f = x - i;
  const c = stops[i].map((v, k) => Math.round(v + (stops[i + 1][k] - v) * f));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
}
