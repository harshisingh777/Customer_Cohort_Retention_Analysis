"use client";

import { useMemo } from "react";
import type { Schemas } from "@/lib/api/types";
import { makeRamp, stepColor, textOnStep } from "@/lib/ramp";
import { useFmt } from "./context";

type Rfm = Schemas["Rfm"];
const R = [1, 2, 3, 4, 5];
const F = [5, 4, 3, 2, 1];

/**
 * 5 x 5 Recency x Frequency. Cell shade = average value, cell text = customer count.
 * Segment regions are outlined and named on the grid; a cell opens its segment's customers.
 */
export function RfmGrid({ data, onSelect }: { data: Rfm; onSelect?: (segment: string) => void }) {
  const fmt = useFmt();
  const cell = useMemo(() => {
    const m = new Map<string, Rfm["cells"][number]>();
    for (const c of data.cells) m.set(`${c.r}:${c.f}`, c);
    return m;
  }, [data.cells]);
  const segAt = (r: number, f: number) => segmentFor(r, f);
  const ramp = makeRamp(Math.max(0, ...data.cells.map((c) => c.avg_value ?? 0)));
  // A segment's name sits in its top-left cell.
  const anchors = new Set<string>();
  const seen = new Set<string>();
  for (const f of F)
    for (const r of R) {
      const s = segAt(r, f);
      if (!seen.has(s)) {
        seen.add(s);
        anchors.add(`${r}:${f}`);
      }
    }
  const border = (r: number, f: number) => {
    const s = segAt(r, f);
    const edge = (rr: number, ff: number) => rr < 1 || rr > 5 || ff < 1 || ff > 5 || segAt(rr, ff) !== s;
    return {
      borderTop: edge(r, f + 1) ? "2px solid var(--ink)" : "1px solid var(--sheet)",
      borderBottom: edge(r, f - 1) ? "2px solid var(--ink)" : "1px solid var(--sheet)",
      borderLeft: edge(r - 1, f) ? "2px solid var(--ink)" : "1px solid var(--sheet)",
      borderRight: edge(r + 1, f) ? "2px solid var(--ink)" : "1px solid var(--sheet)",
    };
  };
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] table-fixed border-collapse text-sm">
        <caption className="sr-only">
          Customers by recency (columns, 1 = longest ago, 5 = most recent) and frequency (rows). Shade shows
          average value per customer.
        </caption>
        <thead>
          <tr>
            <th scope="col" className="w-20 pb-2 text-left font-normal text-graphite">
              Orders
            </th>
            {R.map((r) => (
              <th key={r} scope="col" className="pb-2 text-center font-normal text-graphite">
                {r === 1 ? "Longest ago" : r === 5 ? "Most recent" : `R${r}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {F.map((f) => (
            <tr key={f}>
              <th scope="row" className="pr-3 text-left font-normal text-graphite">
                {["", "1", "2", "3", "4–5", "6+"][f]}
              </th>
              {R.map((r) => {
                const c = cell.get(`${r}:${f}`);
                const seg = segAt(r, f);
                const step = ramp(c?.avg_value ?? 0);
                const label = c
                  ? `${seg}: ${fmt.count(c.customers)} customers, average value ${fmt.money(c.avg_value)}`
                  : `${seg}: no customers`;
                return (
                  <td key={r} className="h-16 p-0" style={border(r, f)}>
                    <button
                      type="button"
                      onClick={() => onSelect?.(seg)}
                      aria-label={label}
                      title={label}
                      className="flex h-full w-full flex-col items-start justify-between p-2 text-left"
                      style={{
                        background: c ? stepColor(step) : "var(--ground)",
                        color: c ? textOnStep(step) : "var(--graphite)",
                      }}
                    >
                      <span className="text-xs leading-tight">{anchors.has(`${r}:${f}`) ? seg : ""}</span>
                      <span className="self-end font-medium">{c ? fmt.count(c.customers) : "0"}</span>
                    </button>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Mirrors macros/settings.sql rfm_segment(r, f). */
export function segmentFor(r: number, f: number): string {
  if (r >= 4 && f >= 4) return "Champions";
  if (r >= 4 && f === 3) return "Loyal";
  if (r === 3 && f >= 3) return "Loyal";
  if (r >= 4 && f === 2) return "Potential loyalists";
  if (r >= 4 && f === 1) return "New customers";
  if (r === 3 && f <= 2) return "Needs attention";
  if (r <= 2 && f >= 4) return "Can't lose them";
  if (r <= 2 && f >= 2) return "At risk";
  return "Lost";
}
