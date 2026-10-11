"use client";

import { useQueryStates } from "nuqs";
import { useRef } from "react";
import { useApi } from "@/lib/api/hooks";
import { cohortQuery } from "@/lib/queries";
import { cohortParsers } from "@/lib/search-params";
import { AppHeaderFilters } from "../app-header-filters";
import { PageHeader } from "../app-shell";
import { CohortTable } from "../cohort-table";
import { useFmt } from "../context";
import { CurveChart } from "../curve-chart";
import { ExportButtons } from "../export-buttons";
import { Findings } from "../findings";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";
import { Toggle } from "../toggle";

export function CohortsView() {
  const fmt = useFmt();
  const [q, setQ] = useQueryStates(cohortParsers, { history: "replace" });
  const query = cohortQuery(q);
  const table = useApi("/v1/cohorts/retention", query, "cohorts");
  const curves = useApi("/v1/cohorts/curves", query, "cohort curves");
  const curveRef = useRef<HTMLDivElement>(null);
  const unit = q.granularity === "month" ? "month" : "week";

  const select = (cohort: string) => {
    setQ({ select: q.select === cohort ? null : cohort });
    curveRef.current?.focus({ preventScroll: true });
  };
  const togglePin = () => {
    if (!q.select) return;
    const pins = q.pin.includes(q.select)
      ? q.pin.filter((p) => p !== q.select)
      : [...q.pin, q.select].slice(-3);
    setQ({ pin: pins });
  };

  const measureCopy = {
    customers: (
      <>
        Share of each cohort that <Term id="retention_rate">bought again</Term> in each {unit} after their
        first order.
      </>
    ),
    revenue: (
      <>
        Each cohort's net revenue in each {unit} as a share of its first {unit}:{" "}
        <Term id="revenue_retention">revenue kept</Term>. It can pass 100%.
      </>
    ),
    cumulative: (
      <>
        Share of each cohort that <Term id="cumulative_repeat">had a second order</Term> by the end of each{" "}
        {unit}. It never falls, so it's the clearest way to compare cohorts.
      </>
    ),
  }[q.measure];

  return (
    <>
      <PageHeader
        title="Cohorts"
        lede={`Of the customers acquired in each ${unit}, how many came back, and when. Rows are cohorts, oldest at the top; columns are ${unit}s since the first order.`}
        filters={<AppHeaderFilters mode="cohorts" />}
        actions={<ExportButtons csvView="cohorts" pdfView="cohorts" params={query} />}
      />
      <div className="flex flex-col gap-6">
        <QueryView query={table} rows={0}>
          {(d) =>
            d.data.findings.length ? (
              <Sheet labelledBy="cohort-findings">
                <SheetHeader title="What stands out" id="cohort-findings" />
                <Findings findings={d.data.findings} />
              </Sheet>
            ) : null
          }
        </QueryView>
        <Sheet labelledBy="table-title">
          <SheetHeader title="Cohort table" id="table-title" description={measureCopy}>
            <Toggle
              label="Measure"
              value={q.measure}
              onChange={(m) => setQ({ measure: m })}
              options={[
                { value: "customers", label: "Customers" },
                { value: "revenue", label: "Revenue" },
                { value: "cumulative", label: "Cumulative repeat" },
              ]}
            />
            <Toggle
              label="Cohort size"
              value={q.granularity}
              onChange={(g) => setQ({ granularity: g, select: null, pin: [] })}
              options={[
                { value: "month", label: "Monthly" },
                { value: "week", label: "Weekly" },
              ]}
            />
          </SheetHeader>
          <SheetBoundary>
            <QueryView
              query={table}
              rows={12}
              isEmpty={(d) => d.data.cohorts.length === 0}
              empty={
                <p className="py-6 text-graphite">
                  No customers match these filters. Widen the filters above.
                </p>
              }
            >
              {(d) => (
                <>
                  <CohortTable
                    table={d.data}
                    selected={q.select}
                    onSelect={select}
                    caption={`${q.granularity === "month" ? "Monthly" : "Weekly"} cohorts by ${unit} since first order`}
                  />
                  <p className="mt-3 text-graphite text-xs">
                    Use the arrow keys to move between cells and Enter to select a cohort. Cohorts under 30
                    customers show muted, unshaded numbers; hover for the interval.
                  </p>
                </>
              )}
            </QueryView>
          </SheetBoundary>
        </Sheet>
        <Sheet labelledBy="curves-title">
          <div ref={curveRef} tabIndex={-1} className="outline-none">
            <SheetHeader
              title="Curves"
              id="curves-title"
              description={
                q.select
                  ? `${fmt.cohort(q.select)} against the median of the last six cohorts and every other cohort.`
                  : "Every cohort in light grey, the median of the last six in dark grey. Select a cohort in the table to compare it."
              }
            >
              {q.select ? (
                <button
                  type="button"
                  onClick={togglePin}
                  className="rounded-[var(--radius-control)] border border-rule px-3 py-1.5 text-sm hover:border-ink"
                >
                  {q.pin.includes(q.select) ? "Unpin" : "Pin for comparison"}
                </button>
              ) : null}
              {q.pin.length ? (
                <button
                  type="button"
                  onClick={() => setQ({ pin: [] })}
                  className="text-graphite text-sm underline underline-offset-4"
                >
                  Clear pins
                </button>
              ) : null}
            </SheetHeader>
            <SheetBoundary>
              <QueryView query={curves} rows={8} isEmpty={(d) => d.data.series.length === 0}>
                {(d) => <CurveChart curves={d.data} selected={q.select} pins={q.pin} />}
              </QueryView>
            </SheetBoundary>
          </div>
        </Sheet>
      </div>
    </>
  );
}
