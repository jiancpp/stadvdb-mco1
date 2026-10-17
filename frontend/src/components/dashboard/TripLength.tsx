"use client";

import { Filters, LengthBand, money0, useApi } from "@/lib/api";
import { Callout, Card, CardHead, ErrorNote } from "../ui";

export default function TripLength({ filters }: { filters: Filters }) {
  const { data, loading, error } = useApi<LengthBand[]>("trip-length", filters);
  const rows = data ?? [];
  const max = Math.max(1, ...rows.map((r) => r.rev_per_hour));
  const best = rows.reduce<LengthBand | null>((a, r) => (!a || r.rev_per_hour > a.rev_per_hour ? r : a), null);
  const first = rows[0];

  return (
    <Card loading={loading}>
      <CardHead title="Trip length sweet spot" sub="Medium-length trips earn most per occupied hour." />
      <ErrorNote message={error} />
      <div className="len len-head"><span>Trip length</span><span>Share</span><span>Avg $/hr (occupied)</span><span /></div>
      {rows.map((r) => (
        <div className="len len-row" key={r.band}>
          <span>{r.band}</span>
          <span>{Math.round(r.share_pct)}%</span>
          <div className="len-bar"><i style={{ width: `${(r.rev_per_hour / max) * 100}%` }} /></div>
          <b>{money0(r.rev_per_hour)}</b>
        </div>
      ))}
      {best && first && (
        <Callout>
          Short trips ({first.band.toLowerCase()}) are {Math.round(first.share_pct)}% of trips and still pay {money0(first.rev_per_hour)}.
          The sweetest band is {best.band.replace(" mi", " miles")} at {money0(best.rev_per_hour)}.
        </Callout>
      )}
    </Card>
  );
}
