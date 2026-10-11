"use client";

import { useRouter } from "next/navigation";
import { useQueryStates } from "nuqs";
import { toSearch } from "@/lib/api/fetcher";
import { useApi } from "@/lib/api/hooks";
import type { Schemas } from "@/lib/api/types";
import { segmentQuery } from "@/lib/queries";
import { dimParsers } from "@/lib/search-params";
import { AppHeaderFilters } from "../app-header-filters";
import { PageHeader } from "../app-shell";
import { useFmt } from "../context";
import { ExportButtons } from "../export-buttons";
import { RfmGrid } from "../rfm-grid";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";

export function SegmentTotals({ d, onSelect }: { d: Schemas["Rfm"]; onSelect?: (s: string) => void }) {
  const fmt = useFmt();
  return (
    <table className="w-full text-sm">
      <caption className="sr-only">Customers per segment</caption>
      <thead>
        <tr className="border-rule border-b text-graphite">
          <th scope="col" className="py-2 pr-3 text-left font-normal">
            Segment
          </th>
          <th scope="col" className="py-2 pr-3 text-right font-normal">
            Customers
          </th>
          <th scope="col" className="py-2 pr-3 text-right font-normal">
            Share
          </th>
          <th scope="col" className="py-2 text-right font-normal">
            Average value
          </th>
        </tr>
      </thead>
      <tbody>
        {d.segments.map((s) => (
          <tr key={s.name} className="border-rule border-b last:border-0">
            <th scope="row" className="py-2 pr-3 text-left font-normal">
              {onSelect ? (
                <button
                  type="button"
                  onClick={() => onSelect(s.name)}
                  className="underline underline-offset-4"
                >
                  {s.name}
                </button>
              ) : (
                s.name
              )}
            </th>
            <td className="py-2 pr-3 text-right">{fmt.count(s.customers)}</td>
            <td className="py-2 pr-3 text-right">{fmt.pct(s.share, 0)}</td>
            <td className="py-2 text-right">{fmt.money(s.avg_value)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function SegmentsView() {
  const router = useRouter();
  const [f] = useQueryStates(dimParsers);
  const q = segmentQuery(f);
  const rfm = useApi("/v1/segments/rfm", q, "segments");
  const open = (segment: string) => router.push(`/customers${toSearch({ ...q, segment })}`);
  return (
    <>
      <PageHeader
        title="Segments"
        lede={
          <>
            Customers grouped by how recently and how often they buy. Click a region to see who's in it.
            Scoring: <Term id="rfm_segment">RFM segment</Term>.
          </>
        }
        filters={<AppHeaderFilters />}
        actions={<ExportButtons csvView="rfm" pdfView="segments" params={q} />}
      />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <Sheet labelledBy="grid-title">
          <SheetHeader
            title="Recency × frequency"
            id="grid-title"
            description="Darker cells hold customers with higher average value. Numbers are customer counts."
          />
          <SheetBoundary>
            <QueryView query={rfm} rows={5} isEmpty={(d) => d.data.total_customers === 0}>
              {(d) => <RfmGrid data={d.data} onSelect={open} />}
            </QueryView>
          </SheetBoundary>
        </Sheet>
        <Sheet labelledBy="totals-title">
          <SheetHeader title="Segments" id="totals-title" />
          <SheetBoundary>
            <QueryView query={rfm} rows={8} isEmpty={(d) => d.data.total_customers === 0}>
              {(d) => <SegmentTotals d={d.data} onSelect={open} />}
            </QueryView>
          </SheetBoundary>
        </Sheet>
      </div>
    </>
  );
}
