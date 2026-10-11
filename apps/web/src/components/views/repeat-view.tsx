"use client";

import { useQueryStates } from "nuqs";
import { useApi } from "@/lib/api/hooks";
import type { Schemas } from "@/lib/api/types";
import { repeatQueries } from "@/lib/queries";
import { repeatParsers } from "@/lib/search-params";
import { AppHeaderFilters } from "../app-header-filters";
import { PageHeader } from "../app-shell";
import { useFmt } from "../context";
import { ExportButtons } from "../export-buttons";
import { Findings } from "../findings";
import { Histogram } from "../histogram";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";
import { Toggle } from "../toggle";

function TimingSentence({ d }: { d: Schemas["SecondOrder"] }) {
  const fmt = useFmt();
  if (!d.repeaters) return <p className="serif text-base">No customer has placed a second order yet.</p>;
  return (
    <p className="serif measure text-base leading-relaxed">
      Of {fmt.count(d.first_buyers)} customers, {fmt.count(d.repeaters)} (
      {fmt.pct(d.repeaters / d.first_buyers)}) placed a second order. Half of them did so within{" "}
      <strong className="font-semibold">{fmt.days(d.median_days)}</strong>, and 9 in 10 within{" "}
      <strong className="font-semibold">{fmt.days(d.p90_days)}</strong>.
    </p>
  );
}

export function FirstProductTable({
  d,
  highlight,
}: {
  d: Schemas["FirstProduct"];
  highlight?: string | null;
}) {
  const fmt = useFmt();
  const noun = d.level === "category" ? "Category" : "Product";
  return (
    <>
      <p className="mb-3 text-graphite text-sm">
        Store average: {fmt.pct(d.store.rate)} of {fmt.count(d.store.eligible)} customers came back within 90
        days.
        {d.hidden_small
          ? ` ${fmt.count(d.hidden_small)} ${d.hidden_small === 1 ? noun.toLowerCase() : d.level === "category" ? "categories" : "products"} with fewer than ${d.min_buyers} eligible customers ${d.hidden_small === 1 ? "is" : "are"} left out.`
          : ""}
      </p>
      <div className="max-h-[560px] overflow-auto">
        <table className="w-full text-sm">
          <caption className="sr-only">
            {noun} of the first order and how often those customers came back within 90 days
          </caption>
          <thead className="sticky top-0 bg-sheet">
            <tr className="border-rule border-b text-graphite">
              <th scope="col" className="py-2 pr-3 text-left font-normal">
                {noun} of first order
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                First-time buyers
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-normal">
                <Term id="repeat_90d">Came back within 90 days</Term>
              </th>
              <th scope="col" className="py-2 text-right font-normal">
                Against store average
              </th>
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r) => (
              <tr key={r.item_id} className="border-rule border-b last:border-0">
                <th
                  scope="row"
                  className="max-w-[320px] truncate py-2 pr-3 text-left font-normal"
                  title={r.label}
                >
                  <span className={highlight === r.item_id ? "highlight" : ""}>{r.label}</span>
                </th>
                <td className="py-2 pr-3 text-right">{fmt.count(r.first_buyers)}</td>
                <td className="py-2 pr-3 text-right">
                  {fmt.pct(r.rate)}
                  <span className="block text-graphite text-xs">
                    {fmt.pct(r.low)}–{fmt.pct(r.high)} of {fmt.count(r.eligible)}
                  </span>
                </td>
                <td className="py-2 text-right">{fmt.pts(r.diff_pts)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

export function RepeatView() {
  const [q, setQ] = useQueryStates(repeatParsers, { history: "replace" });
  const { dims, firstProduct } = repeatQueries(q);
  const timing = useApi("/v1/repeat/second-order", dims, "time to second order");
  const fp = useApi("/v1/repeat/first-product", firstProduct, "first purchases");
  return (
    <>
      <PageHeader
        title="Repeat"
        lede="How long customers take to come back, and which first purchase brings them back."
        filters={<AppHeaderFilters />}
        actions={<ExportButtons csvView="first_product" pdfView="repeat" params={firstProduct} />}
      />
      <div className="flex flex-col gap-6">
        <Sheet labelledBy="timing-title">
          <SheetHeader
            title={<Term id="time_to_second_order">Time to second order</Term>}
            id="timing-title"
          />
          <SheetBoundary>
            <QueryView query={timing} rows={6}>
              {(d) => (
                <div className="flex flex-col gap-4">
                  <TimingSentence d={d.data} />
                  {d.data.repeaters ? <Histogram data={d.data} /> : null}
                </div>
              )}
            </QueryView>
          </SheetBoundary>
        </Sheet>
        <Sheet labelledBy="first-title">
          <SheetHeader
            title="First purchase → repeat"
            id="first-title"
            description="Sorted by how far each differs from the store average. Only items with at least 30 customers old enough to have had 90 days."
          >
            <Toggle
              label="Group by"
              value={q.level}
              onChange={(level) => setQ({ level, highlight: null })}
              options={[
                { value: "category", label: "Category" },
                { value: "product", label: "Product" },
              ]}
            />
          </SheetHeader>
          <SheetBoundary>
            <QueryView
              query={fp}
              rows={10}
              isEmpty={(d) => d.data.rows.length === 0}
              empty={
                <p className="py-6 text-graphite">
                  No {q.level} has 30 or more customers old enough to judge. Widen the date range.
                </p>
              }
            >
              {(d) => (
                <div className="flex flex-col gap-5">
                  {d.data.findings.length ? <Findings findings={d.data.findings} /> : null}
                  <FirstProductTable d={d.data} highlight={q.highlight} />
                </div>
              )}
            </QueryView>
          </SheetBoundary>
        </Sheet>
      </div>
    </>
  );
}
