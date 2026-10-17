"use client";

import { useEffect, useState } from "react";

export type DayType = "all" | "weekday" | "weekend";
export interface Filters {
  start: string; // YYYY-MM-DD
  end: string;
  borough: string | null;
  dayType: DayType;
}

/* ---- response types: mirror backend/app/routers/opportunities.py ---- */
export interface Kpi { value: number | null; delta_pct: number | null; series: number[] }
export interface KpiResponse {
  rev_per_hour: Kpi;
  rev_per_mile: Kpi;
  avg_revenue: { month: Kpi; day: Kpi };
  avg_trips: { month: Kpi; day: Kpi };
}
export interface ZonePoint {
  name: string; borough: string; trips: number; rev_per_hour: number; net_flow_pct: number; labeled: boolean;
}
export interface ZoneResponse { level: "zone" | "borough"; avg_rev_per_hour: number | null; points: ZonePoint[] }
export interface Corridor {
  rank: number; from_zone: string; to_zone: string; trips_per_day: number; rev_per_hour: number; return_flow_pct: number;
}
export interface LengthBand { band: string; share_pct: number; rev_per_hour: number }
export interface SlowPoint { label: string; rev_per_hour: number; avg_mph: number }
export interface SlowResponse {
  points: SlowPoint[];
  slow_window: { from: string; to: string; avg_mph: number; rev_per_hour: number } | null;
  yield_ratio: number | null;
}
export interface MonthDemand { month: string; year: number; trips_per_day: number; pct_vs_avg: number | null }
export interface DemandResponse { avg_trips_per_day: number | null; months: MonthDemand[] }
export interface FilterMeta { boroughs: string[]; min_date: string; max_date: string }

/* ---- formatters ---- */
const compactFmt = new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 });
export const compact = (n: number) => compactFmt.format(n);
export const money0 = (n: number) => `$${Math.round(n).toLocaleString("en-US")}`;
export const moneyCompact = (n: number) => `$${compact(n)}`;
export const signedPct = (n: number, digits = 1) => `${n >= 0 ? "+" : ""}${n.toFixed(digits)}%`;

/* ---- data hooks ---- */
type State<T> = { data: T | null; loading: boolean; error: string | null };

function useFetch<T>(url: string): State<T> {
  const [state, setState] = useState<State<T>>({ data: null, loading: true, error: null });
  useEffect(() => {
    const ctl = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fetch(url, { signal: ctl.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
        return r.json() as Promise<T>;
      })
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setState((s) => ({ ...s, loading: false, error: e.message }));
      });
    return () => ctl.abort();
  }, [url]);
  return state;
}

export function useApi<T>(path: string, f: Filters, extra: Record<string, string> = {}): State<T> {
  const params = new URLSearchParams({ start: f.start, end: f.end, day_type: f.dayType, ...extra });
  if (f.borough) params.set("borough", f.borough);
  return useFetch<T>(`/api/opportunities/${path}?${params}`);
}

export const useFilterMeta = () => useFetch<FilterMeta>("/api/opportunities/filters");
