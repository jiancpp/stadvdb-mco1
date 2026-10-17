"use client";

import { useEffect, useRef, useState } from "react";
import { DayType, Filters, useFilterMeta } from "@/lib/api";
import Kpis from "./Kpis";
import MonthlyDemand from "./MonthlyDemand";
import SlowWindows from "./SlowWindows";
import TopCorridors from "./TopCorridors";
import TripLength from "./TripLength";
import ZoneBubbleChart from "./ZoneBubbleChart";

const fmt = (iso: string, year: boolean) =>
  new Date(`${iso}T00:00:00`).toLocaleDateString("en-US", { month: "short", day: "numeric", ...(year ? { year: "numeric" } : {}) });
const rangeLabel = (a: string, b: string) => `${fmt(a, a.slice(0, 4) !== b.slice(0, 4))} – ${fmt(b, true)}`;

export default function Dashboard() {
  const [filters, setFilters] = useState<Filters>({ start: "2025-01-01", end: "2025-12-31", borough: null, dayType: "all" });
  const [open, setOpen] = useState(false);
  const popRef = useRef<HTMLDivElement>(null);
  const { data: meta } = useFilterMeta();
  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));

  useEffect(() => {
    const close = (e: MouseEvent) => popRef.current && !popRef.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  return (
    <main className="dash">
      <div className="hero">
        <div>
          <h1>NYC Taxi<br />Opportunities &amp; Efficiency</h1>
          <p>Where an hour of driving pays most, and what wastes it.</p>
        </div>
        <div className="filters">
          <div className="pop-anchor" ref={popRef}>
            <button className="pill" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M3 10h18M8 3v4M16 3v4" /></svg>
              {rangeLabel(filters.start, filters.end)}
              <span className="caret">⌄</span>
            </button>
            {open && (
              <div className="popover">
                <label>From<input type="date" value={filters.start} min={meta?.min_date} max={meta?.max_date}
                  onChange={(e) => e.target.value && set({ start: e.target.value, end: e.target.value > filters.end ? e.target.value : filters.end })} /></label>
                <label>To<input type="date" value={filters.end} min={meta?.min_date} max={meta?.max_date}
                  onChange={(e) => e.target.value && set({ end: e.target.value, start: e.target.value < filters.start ? e.target.value : filters.start })} /></label>
              </div>
            )}
          </div>
          <label className="pill select">
            <span>Borough</span>
            <select value={filters.borough ?? ""} onChange={(e) => set({ borough: e.target.value || null })}>
              <option value="">All boroughs</option>
              {meta?.boroughs.map((b) => <option key={b} value={b}>{b}</option>)}
            </select>
          </label>
          <label className="pill select">
            <span>Day type</span>
            <select value={filters.dayType} onChange={(e) => set({ dayType: e.target.value as DayType })}>
              <option value="all">All days</option>
              <option value="weekday">Weekdays</option>
              <option value="weekend">Weekends</option>
            </select>
          </label>
        </div>
      </div>

      <Kpis filters={filters} />
      <div className="grid g-2a"><ZoneBubbleChart filters={filters} /><TopCorridors filters={filters} /></div>
      <div className="grid g-2b"><TripLength filters={filters} /><SlowWindows filters={filters} /></div>
      <MonthlyDemand filters={filters} />
    </main>
  );
}
