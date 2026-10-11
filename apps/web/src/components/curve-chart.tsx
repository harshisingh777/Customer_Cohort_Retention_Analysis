"use client";

import { Group } from "@visx/group";
import { LinePath } from "@visx/shape";
import { scaleLinear } from "d3-scale";
import type { Schemas } from "@/lib/api/types";
import { useWidth } from "@/lib/use-width";
import { useFmt } from "./context";

type Curves = Schemas["Curves"];
const DASHES = ["", "6 4", "1.5 3"]; // pinned comparisons differ by dash pattern, not colour

/**
 * All cohorts 1 px in `rule`; the median of the last six 2 px in `graphite`; the selected
 * cohort 2 px in `ink` with a highlighter halo. Four gridlines, no border, no legend box:
 * labels sit at the line ends.
 */
export function CurveChart({
  curves,
  selected,
  pins = [],
  height = 300,
}: {
  curves: Curves;
  selected?: string | null;
  pins?: string[];
  height?: number;
}) {
  const fmt = useFmt();
  const [ref, width] = useWidth<HTMLDivElement>();
  // Customer retention is 100% at period 0 by construction; start the axis at 1.
  const start = curves.measure === "customers" ? 1 : 0;
  const periods = curves.periods.filter((p) => p >= start);
  const margin = { top: 12, right: 132, bottom: 28, left: 44 };
  const w = Math.max(200, width - margin.left - margin.right);
  const h = height - margin.top - margin.bottom;
  const maxY = Math.max(
    0.05,
    ...curves.series.flatMap((s) => s.values.slice(start).map((v) => v ?? 0)),
    ...curves.median.slice(start).map((v) => v ?? 0),
  );
  const x = scaleLinear()
    .domain([start, Math.max(start + 1, periods[periods.length - 1] ?? start + 1)])
    .range([0, w]);
  const y = scaleLinear().domain([0, maxY]).nice(4).range([h, 0]);
  const ticks = y.ticks(4);
  const xTicks = x.ticks(Math.min(periods.length, Math.floor(w / 60))).filter(Number.isInteger);

  type Pt = { p: number; v: number };
  const points = (values: (number | null)[]): Pt[] =>
    values.map((v, p) => ({ p, v: v as number })).filter((d) => d.p >= start && d.v != null);

  const sel = curves.series.find((s) => s.cohort === selected);
  const pinned = pins
    .map((c) => curves.series.find((s) => s.cohort === c))
    .filter((s): s is NonNullable<typeof s> => Boolean(s) && s?.cohort !== selected)
    .slice(0, 3);
  const unit = curves.granularity === "month" ? "Months" : "Weeks";

  const endLabel = (values: (number | null)[], text: string, bold = false) => {
    const pts = points(values);
    const last = pts[pts.length - 1];
    if (!last) return null;
    return (
      <text
        x={x(last.p) + 6}
        y={y(last.v)}
        dy="0.32em"
        fontSize={12}
        fontWeight={bold ? 600 : 400}
        fill={bold ? "var(--ink)" : "var(--graphite)"}
      >
        {text} {fmt.pct(last.v, 0)}
      </text>
    );
  };

  const describe = [
    sel ? `${fmt.cohort(sel.cohort)} cohort selected.` : "",
    curves.median.some((v) => v != null) ? "Median of the last six cohorts shown in grey." : "",
  ].join(" ");

  return (
    <div ref={ref} className="w-full">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label={`${curves.series.length} cohort curves by ${unit.toLowerCase()} since first order. ${describe}`}
      >
        <Group left={margin.left} top={margin.top}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={0} x2={w} y1={y(t)} y2={y(t)} stroke="var(--rule)" strokeWidth={1} />
              <text x={-8} y={y(t)} dy="0.32em" textAnchor="end" fontSize={12} fill="var(--graphite)">
                {fmt.pct(t, 0)}
              </text>
            </g>
          ))}
          {xTicks.map((t) => (
            <text key={t} x={x(t)} y={h + 18} textAnchor="middle" fontSize={12} fill="var(--graphite)">
              {t}
            </text>
          ))}
          <text x={w} y={h + 18} dx={8} fontSize={12} fill="var(--graphite)">
            {unit.toLowerCase()}
          </text>
          {curves.series.map((s) => (
            <LinePath<Pt>
              key={s.cohort}
              data={points(s.values)}
              x={(d) => x(d.p)}
              y={(d) => y(d.v)}
              stroke="var(--rule)"
              strokeWidth={1}
            />
          ))}
          <LinePath<Pt>
            data={points(curves.median)}
            x={(d) => x(d.p)}
            y={(d) => y(d.v)}
            stroke="var(--graphite)"
            strokeWidth={2}
          />
          {endLabel(curves.median, "Median of last 6")}
          {pinned.map((s, i) => (
            <g key={s.cohort}>
              <LinePath<Pt>
                data={points(s.values)}
                x={(d) => x(d.p)}
                y={(d) => y(d.v)}
                stroke="var(--ink)"
                strokeWidth={1.5}
                strokeDasharray={DASHES[i]}
              />
              {endLabel(s.values, fmt.cohort(s.cohort))}
            </g>
          ))}
          {sel ? (
            <g className="fade-in">
              <LinePath<Pt>
                data={points(sel.values)}
                x={(d) => x(d.p)}
                y={(d) => y(d.v)}
                stroke="var(--highlighter)"
                strokeWidth={7}
                strokeLinecap="round"
              />
              <LinePath<Pt>
                data={points(sel.values)}
                x={(d) => x(d.p)}
                y={(d) => y(d.v)}
                stroke="var(--ink)"
                strokeWidth={2}
              />
              {endLabel(sel.values, fmt.cohort(sel.cohort), true)}
            </g>
          ) : null}
        </Group>
      </svg>
    </div>
  );
}
