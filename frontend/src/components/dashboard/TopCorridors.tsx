"use client";

import { Corridor, Filters, money0, compact, useApi } from "@/lib/api";
import { Callout, Card, CardHead, ErrorNote, heat } from "../ui";

const perDay = (n: number) => compact(n).replace("K", "k");

export default function TopCorridors({ filters }: { filters: Filters }) {
  const { data, loading, error } = useApi<Corridor[]>("corridors", filters);
  const rows = data ?? [];
  const max = Math.max(1, ...rows.map((r) => r.trips_per_day));
  const low = rows.filter((r) => r.return_flow_pct < 25);
  const top = rows[0];

  return (
    <Card loading={loading}>
      <CardHead title="Top corridors" sub="Busiest pickup-to-dropoff routes, and how much traffic comes back." />
      <ErrorNote message={error} />
      <div className="corr corr-head">
        <span>From → To</span><span>Trips per day</span><span>$/hr</span><span>Return flow</span>
      </div>
      {rows.map((r, i) => (
        <div className="corr corr-row" key={`${r.from_zone}-${r.to_zone}`}>
          <div className="corr-name">
            <b className="rank" style={{ background: heat(1 - i / 5) }}>{r.rank}</b>
            <div><span>{r.from_zone}</span><span>→ {r.to_zone}</span></div>
          </div>
          <div className="corr-bar"><i style={{ width: `${(r.trips_per_day / max) * 100}%` }} /><span>{perDay(r.trips_per_day)}</span></div>
          <b>{money0(r.rev_per_hour)}</b>
          <b className={r.return_flow_pct < 25 ? "bad" : ""}>{Math.round(r.return_flow_pct)}%</b>
        </div>
      ))}
      {top && (
        <Callout>
          <ul>
            <li>{top.from_zone} to {top.to_zone} is the busiest route, and {Math.round(top.return_flow_pct)}% of fleet returns there.</li>
            {low.length > 0 && (
              <li>
                Trips from {low.map((r) => r.from_zone).join(" and ")} pay up to {money0(Math.max(...low.map((r) => r.rev_per_hour)))} per hour,
                but only {Math.round(Math.min(...low.map((r) => r.return_flow_pct)))}% to {Math.round(Math.max(...low.map((r) => r.return_flow_pct)))}% comes
                back, so expect an empty ride home.
              </li>
            )}
          </ul>
        </Callout>
      )}
    </Card>
  );
}
