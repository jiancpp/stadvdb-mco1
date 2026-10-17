"use client";

import { useState, type ReactNode } from "react";
import { Filters, Kpi, KpiResponse, compact, moneyCompact, signedPct, useApi } from "@/lib/api";
import { Card, ErrorNote, Spark, Toggle } from "../ui";

type Grain = "month" | "day";
const GRAINS: { value: Grain; label: string }[] = [
  { value: "month", label: "Month" },
  { value: "day", label: "Day" },
];

const DECO = {
  dollar: (
    <svg viewBox="0 0 64 64"><text x="32" y="52" textAnchor="middle" fontSize="64" fontWeight="800" fill="currentColor">$</text></svg>
  ),
  pin: (
    <svg viewBox="0 0 64 64"><path fill="currentColor" fillRule="evenodd" d="M32 4C20 4 12 13 12 24c0 15 20 36 20 36s20-21 20-36C52 13 44 4 32 4Zm0 12a8 8 0 1 1 0 16a8 8 0 0 1 0-16Z" /></svg>
  ),
  bars: (
    <svg viewBox="0 0 64 64" fill="currentColor"><rect x="8" y="34" width="12" height="22" rx="3" /><rect x="26" y="18" width="12" height="38" rx="3" /><rect x="44" y="6" width="12" height="50" rx="3" /></svg>
  ),
  car: (
    <svg viewBox="0 0 64 64"><path fill="currentColor" d="M8 38l6-16a6 6 0 0 1 5.6-4h24.8a6 6 0 0 1 5.6 4l6 16v14a3 3 0 0 1-3 3h-4a3 3 0 0 1-3-3v-3H18v3a3 3 0 0 1-3 3h-4a3 3 0 0 1-3-3Z" /></svg>
  ),
};

const show = (v: number | null | undefined, fmt: (n: number) => string) => (v == null ? "—" : fmt(v));

function KpiCard(props: {
  label: string; display: string; kpi?: Kpi; color: string; deco: ReactNode; baseline: string; toggle?: ReactNode;
}) {
  const d = props.kpi?.delta_pct;
  const up = (d ?? 0) >= 0;
  return (
    <Card className="kpi">
      <div className="kpi-deco" style={{ color: props.color }}>{props.deco}</div>
      <div className="kpi-label">{props.label}</div>
      {props.toggle}
      <div className="kpi-value">{props.display}</div>
      <div className={`kpi-delta ${d == null ? "" : up ? "up" : "down"}`}>
        {d != null && (<><span>{up ? "▲" : "▼"}</span> {signedPct(d)} <em>{props.baseline}</em></>)}
      </div>
      <Spark data={props.kpi?.series ?? []} color={props.color} />
    </Card>
  );
}

export default function Kpis({ filters }: { filters: Filters }) {
  const { data, loading, error } = useApi<KpiResponse>("kpis", filters);
  const [revGrain, setRevGrain] = useState<Grain>("month");
  const [tripGrain, setTripGrain] = useState<Grain>("month");
  const vs = (g: Grain) => `vs. previous ${g}`;

  return (
    <>
      <ErrorNote message={error} />
      <div className={`kpis ${loading ? "is-loading" : ""}`}>
        <KpiCard label="Revenue per occupied hour" deco={DECO.dollar} color="#f5b301" baseline="vs. Q1"
          kpi={data?.rev_per_hour} display={show(data?.rev_per_hour.value, (n) => `$${n.toFixed(2)}`)} />
        <KpiCard label="Revenue per mile" deco={DECO.pin} color="#e11d2e" baseline="vs. Q1"
          kpi={data?.rev_per_mile} display={show(data?.rev_per_mile.value, (n) => `$${n.toFixed(2)}`)} />
        <KpiCard label="Average revenue" deco={DECO.bars} color="#f59e0b" baseline={vs(revGrain)}
          toggle={<Toggle options={GRAINS} value={revGrain} onChange={setRevGrain} />}
          kpi={data?.avg_revenue[revGrain]} display={show(data?.avg_revenue[revGrain].value, moneyCompact)} />
        <KpiCard label="Average trip volume" deco={DECO.car} color="#e11d2e" baseline={vs(tripGrain)}
          toggle={<Toggle options={GRAINS} value={tripGrain} onChange={setTripGrain} />}
          kpi={data?.avg_trips[tripGrain]} display={show(data?.avg_trips[tripGrain].value, compact)} />
      </div>
    </>
  );
}
