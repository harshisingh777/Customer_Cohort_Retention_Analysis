"use client";

import Link from "next/link";
import { useQueryStates } from "nuqs";
import { useApi } from "@/lib/api/hooks";
import type { Schemas } from "@/lib/api/types";
import { channelQuery } from "@/lib/queries";
import { channelParsers } from "@/lib/search-params";
import { AppHeaderFilters } from "../app-header-filters";
import { PageHeader } from "../app-shell";
import { useDisplay } from "../context";
import { ExportButtons } from "../export-buttons";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";

export function ChannelsTable({ d }: { d: Schemas["Channels"] }) {
  const { fmt, isAdmin } = useDisplay();
  const spend = d.has_spend;
  const payback = spend && d.gross_margin != null;
  const th = "py-2 pr-3 text-right font-normal";
  return (
    <>
      <p className="mb-3">
        {fmt.pct(d.coverage.share, 0)} of new customers have a known{" "}
        <Term id="attribution_coverage">acquisition channel</Term>.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <caption className="sr-only">Channel performance</caption>
          <thead>
            <tr className="border-rule border-b text-graphite">
              <th scope="col" className="py-2 pr-3 text-left font-normal">
                Channel
              </th>
              <th scope="col" className={th}>
                <Term id="new_customers">New customers</Term>
              </th>
              {spend ? (
                <th scope="col" className={th}>
                  <Term id="cac">CAC</Term>
                </th>
              ) : null}
              <th scope="col" className={th}>
                <Term id="historical_ltv">365-day LTV</Term>
              </th>
              {d.clv_visible ? (
                <th scope="col" className={th}>
                  <Term id="predicted_ltv_12m">Next 12 months</Term>
                </th>
              ) : null}
              {spend ? (
                <th scope="col" className={th}>
                  <Term id="ltv_cac">LTV:CAC</Term>
                </th>
              ) : null}
              {payback ? (
                <th scope="col" className="py-2 text-right font-normal">
                  <Term id="payback_month">Pays back in</Term>
                </th>
              ) : null}
            </tr>
          </thead>
          <tbody>
            {d.rows.map((r) => (
              <tr key={r.channel} className="border-rule border-b last:border-0">
                <th scope="row" className="py-2 pr-3 text-left font-normal">
                  {r.channel === "unattributed" ? "Unknown channel" : r.channel}
                </th>
                <td className="py-2 pr-3 text-right">{fmt.count(r.new_customers)}</td>
                {spend ? (
                  <td className="py-2 pr-3 text-right">{r.cac == null ? "–" : fmt.money(r.cac, true)}</td>
                ) : null}
                <td className="py-2 pr-3 text-right">
                  {fmt.money(r.ltv_365)}
                  {r.ltv_basis === "predicted" ? (
                    <span className="block text-graphite text-xs">predicted</span>
                  ) : null}
                </td>
                {d.clv_visible ? (
                  <td className="py-2 pr-3 text-right">
                    {r.pred_ltv_p10 == null
                      ? "–"
                      : `${fmt.money(r.pred_ltv_p10)}–${fmt.money(r.pred_ltv_p90)}`}
                  </td>
                ) : null}
                {spend ? <td className="py-2 pr-3 text-right">{fmt.ratio(r.ltv_cac)}</td> : null}
                {payback ? (
                  <td className="py-2 text-right">
                    {r.cac == null ? "–" : r.payback_month == null ? "Not yet" : `Month ${r.payback_month}`}
                  </td>
                ) : null}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 flex flex-col gap-1 text-graphite text-sm">
        {!spend ? (
          <p>
            Add marketing spend to see CAC, LTV:CAC and payback: load a CSV of date, channel and spend_amount
            with <code className="font-ui">just spend path/to/spend.csv</code>, then refresh.
          </p>
        ) : null}
        {spend && d.gross_margin == null ? (
          <p>
            Payback needs a gross margin.{" "}
            {isAdmin ? (
              <Link href="/settings" className="underline underline-offset-4">
                Set it in Settings.
              </Link>
            ) : (
              "Ask an admin to set it in Settings."
            )}
          </p>
        ) : null}
        {payback ? (
          <p>Payback assumes a {fmt.pct(d.gross_margin, 0)} gross margin, set in Settings.</p>
        ) : null}
        {!d.clv_visible && d.clv_hidden_reason ? <p>{d.clv_hidden_reason}</p> : null}
      </div>
    </>
  );
}

export function ChannelsView() {
  const [f] = useQueryStates(channelParsers);
  const q = channelQuery(f);
  const channels = useApi("/v1/channels", q, "channels");
  return (
    <>
      <PageHeader
        title="Channels"
        lede="Which acquisition channels bring customers worth more than they cost, and when those customers pay back."
        filters={
          <AppHeaderFilters
            mode="range"
            note="Spend is recorded per channel, so country and category filters don't apply here."
          />
        }
        actions={<ExportButtons csvView="channels" pdfView="channels" params={q} />}
      />
      <Sheet labelledBy="channels-title">
        <SheetHeader title="Channel performance" id="channels-title" />
        <SheetBoundary>
          <QueryView query={channels} rows={6} isEmpty={(d) => d.data.rows.length === 0}>
            {(d) => <ChannelsTable d={d.data} />}
          </QueryView>
        </SheetBoundary>
      </Sheet>
    </>
  );
}
