"use client";

import type { Schemas } from "@/lib/api/types";
import { useFmt } from "./context";
import { Term } from "./term";

type Vital = Schemas["Vital"];

/** Not a row of KPI cards: a small table, each metric against its own previous period. */
export function VitalsTable({ vitals }: { vitals: Vital[] }) {
  const fmt = useFmt();
  const value = (v: Vital, x: number | null | undefined) =>
    v.kind === "rate" ? fmt.pct(x) : v.kind === "currency" ? fmt.money(x) : fmt.count(x);
  const change = (v: Vital) => {
    if (!v.change) return "–";
    const c = v.change as { value: number; unit: "pts" | "pct" };
    return c.unit === "pts" ? fmt.pts(c.value) : fmt.pctChange(c.value);
  };
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Vitals: latest period against the one before</caption>
      <thead>
        <tr className="border-rule border-b text-graphite">
          <th scope="col" className="py-2 pr-4 text-left font-normal">
            Measure
          </th>
          <th scope="col" className="py-2 pr-4 text-right font-normal">
            Latest
          </th>
          <th scope="col" className="py-2 pr-4 text-right font-normal">
            Before
          </th>
          <th scope="col" className="py-2 text-right font-normal">
            Change
          </th>
        </tr>
      </thead>
      <tbody>
        {vitals.map((v) => (
          <tr key={v.id} className="border-rule border-b last:border-0">
            <th scope="row" className="py-2.5 pr-4 text-left font-normal">
              <Term id={v.metric_id}>{v.label}</Term>
            </th>
            <td className="py-2.5 pr-4 text-right">
              <span className="font-medium">{v.current ? value(v, v.current.value) : "–"}</span>
              {v.current ? <span className="block text-graphite text-xs">{v.current.label}</span> : null}
            </td>
            <td className="py-2.5 pr-4 text-right">
              <span>{v.previous ? value(v, v.previous.value) : "–"}</span>
              {v.previous ? <span className="block text-graphite text-xs">{v.previous.label}</span> : null}
            </td>
            <td className="py-2.5 text-right">{change(v)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
