"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import type { CohortRow, Schemas } from "@/lib/api/types";
import type { Format } from "@/lib/format";
import { makeRamp, stepColor, textOnStep } from "@/lib/ramp";
import { useFmt } from "./context";

type Table = Schemas["CohortTable"];
const SMALL_N = 30;

function sentence(fmt: Format, t: Table, row: CohortRow, p: number): string {
  const unit = t.granularity === "month" ? "month" : "week";
  const rate = row.rate[p];
  if (rate == null) return "";
  if (t.measure === "revenue") {
    const base = row.active[0] ?? 0;
    return `${fmt.cohort(row.cohort)} cohort: ${unit} ${p} revenue was ${fmt.pct(rate, 0)} of ${unit} 0 (${fmt.money(row.active[p])} vs ${fmt.money(base)}).`;
  }
  const k = row.active[p] ?? 0;
  const ci =
    row.low[p] != null && row.high[p] != null ? `, ${fmt.pct(row.low[p])}–${fmt.pct(row.high[p])}` : "";
  const verb =
    t.measure === "cumulative" ? `had a second order by ${unit} ${p}` : `bought again in ${unit} ${p}`;
  return `${fmt.count(k)} of ${fmt.count(row.size)} customers ${verb} (${fmt.pct(rate)}${ci}).`;
}

/**
 * The cohort table is an HTML table: keyboard-navigable, screen-reader friendly, copyable.
 * - First data column is cohort size with an inline bar, not "100%".
 * - The colour scale starts at period 1. Unobservable cells are empty ground: a staircase.
 * - Observed zeros show "0%" on the lightest step. Small denominators drop the fill.
 * - Arrow keys move between cells; Enter selects the cohort row.
 */
export function CohortTable({
  table,
  selected,
  onSelect,
  maxPeriods,
  caption,
}: {
  table: Table;
  selected?: string | null;
  onSelect?: (cohort: string) => void;
  maxPeriods?: number;
  caption: string;
}) {
  const fmt = useFmt();
  const periods = table.periods.slice(1, maxPeriods ? maxPeriods + 1 : undefined);
  const rows = table.cohorts;
  const maxSize = Math.max(1, ...rows.map((r) => r.size));
  const ramp = useMemo(() => {
    let max = 0;
    for (const r of rows) for (let p = 1; p < r.rate.length; p++) max = Math.max(max, r.rate[p] ?? 0);
    return makeRamp(max);
  }, [rows]);
  const unit = table.granularity === "month" ? "Months" : "Weeks";

  const [focus, setFocus] = useState<{ r: number; c: number }>({ r: 0, c: 0 });
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const cells = useRef(new Map<string, HTMLElement>());
  const ncols = periods.length + 2;

  const move = useCallback(
    (r: number, c: number) => {
      const nr = Math.max(0, Math.min(rows.length - 1, r));
      const nc = Math.max(0, Math.min(ncols - 1, c));
      setFocus({ r: nr, c: nc });
      cells.current.get(`${nr}:${nc}`)?.focus();
    },
    [rows.length, ncols],
  );

  const onKeyDown = (e: React.KeyboardEvent, r: number, c: number) => {
    const keys: Record<string, [number, number]> = {
      ArrowUp: [r - 1, c],
      ArrowDown: [r + 1, c],
      ArrowLeft: [r, c - 1],
      ArrowRight: [r, c + 1],
      Home: [r, 0],
      End: [r, ncols - 1],
    };
    const target = keys[e.key];
    if (target) {
      e.preventDefault();
      move(...target);
    } else if ((e.key === "Enter" || e.key === " ") && onSelect) {
      e.preventDefault();
      onSelect(rows[r]!.cohort);
    }
  };

  const showTip = (el: HTMLElement, text: string) => {
    const box = wrap.current?.getBoundingClientRect();
    const b = el.getBoundingClientRect();
    if (!box || !text) return;
    setTip({
      text,
      x: b.left - box.left + (wrap.current?.scrollLeft ?? 0) + b.width / 2,
      y: b.top - box.top,
    });
  };

  const reg = (r: number, c: number) => (el: HTMLElement | null) => {
    if (el) cells.current.set(`${r}:${c}`, el);
    else cells.current.delete(`${r}:${c}`);
  };
  const focusProps = (r: number, c: number, text: string) => ({
    ref: reg(r, c),
    tabIndex: focus.r === r && focus.c === c ? 0 : -1,
    onKeyDown: (e: React.KeyboardEvent) => onKeyDown(e, r, c),
    onFocus: (e: React.FocusEvent<HTMLElement>) => {
      setFocus({ r, c });
      showTip(e.currentTarget, text);
    },
    onBlur: () => setTip(null),
    onMouseEnter: (e: React.MouseEvent<HTMLElement>) => showTip(e.currentTarget, text),
    onMouseLeave: () => setTip(null),
  });

  return (
    <div ref={wrap} className="relative overflow-x-auto">
      <table
        className="w-full border-separate border-spacing-0 text-xs sm:text-sm"
        aria-rowcount={rows.length + 1}
      >
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky left-0 z-10 bg-sheet py-1 pr-3 text-left font-normal text-graphite"
            >
              Cohort
            </th>
            <th scope="col" className="py-1 pr-3 text-right font-normal text-graphite">
              Customers
            </th>
            {periods.map((p) => (
              <th
                key={p}
                scope="col"
                className="min-w-[3.25rem] px-1 py-1 text-right font-normal text-graphite"
                aria-label={`${unit.slice(0, -1)} ${p}`}
              >
                {p}
              </th>
            ))}
          </tr>
          <tr>
            <td />
            <td />
            <td colSpan={periods.length} className="pb-1 text-graphite text-xs">
              {unit} since first order
            </td>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, r) => {
            const isSel = selected === row.cohort;
            return (
              <tr key={row.cohort} aria-selected={isSel}>
                <th
                  scope="row"
                  {...focusProps(r, 0, onSelect ? `Select the ${fmt.cohort(row.cohort)} cohort` : "")}
                  onClick={() => onSelect?.(row.cohort)}
                  className={`sticky left-0 z-10 cursor-pointer whitespace-nowrap bg-sheet py-1 pr-3 text-left font-normal ${isSel ? "font-semibold" : ""}`}
                >
                  <span className={isSel ? "highlight" : ""}>{fmt.cohort(row.cohort)}</span>
                </th>
                <td
                  {...focusProps(
                    r,
                    1,
                    `${fmt.count(row.size)} customers in the ${fmt.cohort(row.cohort)} cohort.`,
                  )}
                  className="py-1 pr-3 text-right"
                  aria-label={`${fmt.count(row.size)} customers`}
                >
                  <div className="flex items-center justify-end gap-2">
                    <span
                      aria-hidden="true"
                      className="hidden h-1 rounded-full bg-graphite/40 sm:block"
                      style={{ width: `${Math.max(2, (row.size / maxSize) * 56)}px` }}
                    />
                    <span>{fmt.count(row.size)}</span>
                  </div>
                </td>
                {periods.map((p, i) => {
                  const c = i + 2;
                  const observable = p < row.rate.length;
                  if (!observable) {
                    return (
                      <td
                        key={p}
                        {...focusProps(r, c, "")}
                        aria-label="Not observable yet"
                        className="bg-ground"
                      />
                    );
                  }
                  const rate = row.rate[p] ?? 0;
                  const small = row.size < SMALL_N;
                  const step = ramp(rate);
                  const text = sentence(fmt, table, row, p);
                  return (
                    <td
                      key={p}
                      {...focusProps(r, c, text)}
                      aria-label={text}
                      className={`px-1 py-1 text-right ${small ? "bg-sheet text-graphite" : ""}`}
                      style={small ? undefined : { background: stepColor(step), color: textOnStep(step) }}
                    >
                      {fmt.pctCell(rate)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      {tip ? (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute z-20 w-max max-w-[280px] -translate-x-1/2 -translate-y-full rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-2 text-ink text-xs shadow-pop"
          style={{ left: tip.x, top: tip.y - 6 }}
        >
          {tip.text}
        </div>
      ) : null}
    </div>
  );
}
