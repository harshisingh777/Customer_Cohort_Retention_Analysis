"use client";

import type { Routes } from "@/lib/api/types";
import { CohortTable } from "./cohort-table";
import { useDisplay } from "./context";
import { CurveChart } from "./curve-chart";
import { Findings } from "./findings";
import { Histogram } from "./histogram";
import { RfmGrid } from "./rfm-grid";
import { Sheet, SheetHeader } from "./sheet";
import { ChannelsTable } from "./views/channels-view";
import { HealthPanels, RunsTable } from "./views/data-view";
import { FirstProductTable } from "./views/repeat-view";
import { SegmentTotals } from "./views/segments-view";
import { VitalsTable } from "./vitals-table";

export type PrintData = {
  summary?: Routes["/v1/summary"];
  cohorts?: Routes["/v1/cohorts/retention"];
  curves?: Routes["/v1/cohorts/curves"];
  timing?: Routes["/v1/repeat/second-order"];
  firstProduct?: Routes["/v1/repeat/first-product"];
  rfm?: Routes["/v1/segments/rfm"];
  channels?: Routes["/v1/channels"];
  health?: Routes["/v1/data-health"];
};

/** Columns that fit an A4 page; the dashboard shows the rest. */
const PRINT_PERIODS = 16;

const TITLES: Record<string, string> = {
  summary: "Summary",
  cohorts: "Cohorts",
  repeat: "Repeat",
  segments: "Segments",
  channels: "Channels",
  data: "Data",
};

/** The PDF: the screen components, no chrome. `data-ready` tells the worker to print. */
export function PrintDocument({ view, data, filters }: { view: string; data: PrintData; filters: string }) {
  const { meta, fmt } = useDisplay();
  return (
    <div data-ready="true" className="mx-auto flex max-w-[1100px] flex-col gap-5 bg-white p-6">
      <header className="border-rule border-b pb-4">
        <p className="text-graphite text-sm">{meta.store_name}</p>
        <h1 className="serif font-semibold text-2xl">{TITLES[view] ?? view}</h1>
        <p className="mt-1 text-graphite text-sm">
          {filters} Data through {fmt.day(meta.data_through)}. Exported {fmt.day(new Date().toISOString())}.
        </p>
      </header>
      {data.summary ? (
        <>
          <Sheet>
            <SheetHeader title="What stands out" />
            <Findings findings={data.summary.data.findings} />
          </Sheet>
          <Sheet>
            <SheetHeader title="Vitals" />
            <VitalsTable vitals={data.summary.data.vitals} />
          </Sheet>
        </>
      ) : null}
      {data.cohorts ? (
        <Sheet>
          <SheetHeader title="Cohort table" />
          <CohortTable
            table={
              view === "summary"
                ? { ...data.cohorts.data, cohorts: data.cohorts.data.cohorts.slice(-12) }
                : data.cohorts.data
            }
            maxPeriods={view === "summary" ? 12 : PRINT_PERIODS}
            caption="Cohort table"
          />
          {view !== "summary" && data.cohorts.data.periods.length - 1 > PRINT_PERIODS ? (
            <p className="mt-2 text-graphite text-xs">
              First {PRINT_PERIODS} months shown. The dashboard has all {data.cohorts.data.periods.length - 1}
              .
            </p>
          ) : null}
        </Sheet>
      ) : null}
      {data.curves ? (
        <Sheet>
          <SheetHeader title="Curves" />
          <CurveChart curves={data.curves.data} />
        </Sheet>
      ) : null}
      {data.timing ? (
        <Sheet>
          <SheetHeader title="Time to second order" />
          <Findings
            findings={data.timing.data.findings}
            emptyText="Too few repeat customers to describe timing."
          />
          <Histogram data={data.timing.data} />
        </Sheet>
      ) : null}
      {data.firstProduct ? (
        <Sheet>
          <SheetHeader title="First purchase → repeat" />
          <FirstProductTable
            d={{ ...data.firstProduct.data, rows: data.firstProduct.data.rows.slice(0, 25) }}
          />
        </Sheet>
      ) : null}
      {data.rfm ? (
        <>
          <Sheet>
            <SheetHeader title="Recency × frequency" />
            <RfmGrid data={data.rfm.data} />
          </Sheet>
          <Sheet>
            <SheetHeader title="Segments" />
            <SegmentTotals d={data.rfm.data} />
          </Sheet>
        </>
      ) : null}
      {data.channels ? (
        <Sheet>
          <SheetHeader title="Channel performance" />
          <ChannelsTable d={data.channels.data} />
        </Sheet>
      ) : null}
      {data.health ? (
        <>
          <HealthPanels d={data.health} />
          <Sheet>
            <SheetHeader title="Last 30 runs" />
            <RunsTable d={data.health} />
          </Sheet>
        </>
      ) : null}
    </div>
  );
}
