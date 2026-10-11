"use client";

import { Group } from "@visx/group";
import { Bar } from "@visx/shape";
import { scaleLinear } from "d3-scale";
import type { Schemas } from "@/lib/api/types";
import { useWidth } from "@/lib/use-width";
import { useFmt } from "./context";

type SecondOrder = Schemas["SecondOrder"];

/** Days to second order in 7-day bins, with the median and 90th percentile marked. */
export function Histogram({ data, height = 240 }: { data: SecondOrder; height?: number }) {
  const fmt = useFmt();
  const [ref, width] = useWidth<HTMLDivElement>();
  const margin = { top: 28, right: 16, bottom: 28, left: 44 };
  const w = Math.max(200, width - margin.left - margin.right);
  const h = height - margin.top - margin.bottom;
  const bins = data.bins;
  const lastStart = bins[bins.length - 1]?.start ?? 182;
  const x = scaleLinear()
    .domain([0, lastStart + 7])
    .range([0, w]);
  const maxN = Math.max(1, ...bins.map((b) => b.customers));
  const y = scaleLinear().domain([0, maxN]).nice(4).range([h, 0]);
  const marker = (days: number | null | undefined, label: string) => {
    if (days == null) return null;
    const px = x(Math.min(days, lastStart) + 0.5);
    return (
      <g>
        <line x1={px} x2={px} y1={-6} y2={h} stroke="var(--ink)" strokeWidth={1.5} />
        <text x={px} y={-12} textAnchor="middle" fontSize={12} fill="var(--ink)">
          {label} {fmt.days(days)}
        </text>
      </g>
    );
  };
  return (
    <div ref={ref} className="w-full">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`Histogram of days to second order. Median ${fmt.days(data.median_days)}, 90th percentile ${fmt.days(data.p90_days)}.`}
      >
        <Group left={margin.left} top={margin.top}>
          {y.ticks(4).map((t) => (
            <g key={t}>
              <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
              <text x={-8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={12} fill="var(--graphite)">
                {fmt.count(t)}
              </text>
            </g>
          ))}
          {bins.map((b) => {
            const x0 = x(b.start);
            const x1 = x(b.end != null ? b.end + 1 : b.start + 7);
            return (
              <Bar
                key={b.start}
                x={x0 + 0.5}
                y={y(b.customers)}
                width={Math.max(1, x1 - x0 - 1)}
                height={h - y(b.customers)}
                fill={b.end == null ? "var(--ramp-3)" : "var(--ramp-5)"}
              >
                <title>
                  {b.end != null ? `Days ${b.start}–${b.end}` : `Day ${b.start} or later`}:{" "}
                  {fmt.count(b.customers)} customers
                </title>
              </Bar>
            );
          })}
          {[0, 30, 60, 90, 120, 150, 180].map((d) => (
            <text key={d} x={x(d)} y={h + 18} textAnchor="middle" fontSize={12} fill="var(--graphite)">
              {d === 180 ? "180+" : d}
            </text>
          ))}
          {marker(data.median_days, "Median")}
          {marker(data.p90_days, "90%")}
        </Group>
      </svg>
    </div>
  );
}
