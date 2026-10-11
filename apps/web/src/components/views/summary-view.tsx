"use client";

import Link from "next/link";
import { useQueryStates } from "nuqs";
import { useApi } from "@/lib/api/hooks";
import { summaryQueries } from "@/lib/queries";
import { dimParsers } from "@/lib/search-params";
import { AppHeaderFilters } from "../app-header-filters";
import { PageHeader } from "../app-shell";
import { CohortTable } from "../cohort-table";
import { ExportButtons } from "../export-buttons";
import { Findings } from "../findings";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";
import { VitalsTable } from "../vitals-table";

export function SummaryView() {
  const [f] = useQueryStates(dimParsers);
  const { dims, cohorts } = summaryQueries(f);
  const summary = useApi("/v1/summary", dims, "the summary");
  const table = useApi("/v1/cohorts/retention", cohorts, "cohorts");
  return (
    <>
      <PageHeader
        title="Summary"
        lede="Are the customers you acquire coming back? What stands out first, then the latest numbers against the period before."
        filters={<AppHeaderFilters />}
        actions={<ExportButtons pdfView="summary" params={dims} />}
      />
      <div className="flex flex-col gap-6">
        <Sheet labelledBy="findings-title">
          <SheetHeader title="What stands out" id="findings-title" />
          <SheetBoundary>
            <QueryView query={summary} rows={3}>
              {(d) => <Findings findings={d.data.findings} />}
            </QueryView>
          </SheetBoundary>
        </Sheet>
        <Sheet labelledBy="vitals-title">
          <SheetHeader
            title="Vitals"
            id="vitals-title"
            description="Each measure uses its latest period with complete data, so 90-day and 365-day numbers are never computed on customers too new to count."
          />
          <SheetBoundary>
            <QueryView query={summary} rows={4}>
              {(d) => <VitalsTable vitals={d.data.vitals} />}
            </QueryView>
          </SheetBoundary>
        </Sheet>
        <Sheet labelledBy="recent-title">
          <SheetHeader
            title="Last 12 cohorts"
            id="recent-title"
            description={
              <>
                Share of each month's new customers who <Term id="retention_rate">bought again</Term> in each
                month after. Blank cells haven't happened yet.
              </>
            }
          >
            <Link href="/cohorts" className="underline underline-offset-4">
              All cohorts
            </Link>
          </SheetHeader>
          <SheetBoundary>
            <QueryView
              query={table}
              rows={8}
              isEmpty={(d) => d.data.cohorts.length === 0}
              empty={
                <p className="py-6 text-graphite">
                  No customers match these filters. Widen the filters above.
                </p>
              }
            >
              {(d) => (
                <CohortTable
                  table={{ ...d.data, cohorts: d.data.cohorts.slice(-12) }}
                  maxPeriods={12}
                  caption="Last 12 monthly cohorts, share who bought again by month since first order"
                />
              )}
            </QueryView>
          </SheetBoundary>
        </Sheet>
      </div>
    </>
  );
}
