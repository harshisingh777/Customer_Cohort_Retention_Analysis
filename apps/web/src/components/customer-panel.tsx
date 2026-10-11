"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "@/lib/api/fetcher";
import { apiKey } from "@/lib/api/keys";
import type { CustomerDetail } from "@/lib/api/types";
import { useWidth } from "@/lib/use-width";
import { useApiContext, useDisplay, useFmt } from "./context";
import { ErrorState, FirstLoad } from "./states";
import { Term } from "./term";

function Timeline({ c }: { c: CustomerDetail }) {
  const fmt = useFmt();
  const [ref, width] = useWidth<HTMLDivElement>(360);
  const orders = c.orders_timeline;
  if (!orders.length) return null;
  const t = (d: string) => new Date(`${d}T00:00:00Z`).getTime();
  const t0 = t(orders[0]!.date);
  const t1 = Math.max(t(c.last_order_date), t0 + 86_400_000);
  const pad = 12;
  const w = width - pad * 2;
  const maxRev = Math.max(...orders.map((o) => o.net_revenue));
  return (
    <div ref={ref}>
      <svg
        width={width}
        height={56}
        role="img"
        aria-label={`${orders.length} orders from ${fmt.day(orders[0]!.date)} to ${fmt.day(c.last_order_date)}`}
      >
        <line x1={pad} x2={width - pad} y1={28} y2={28} stroke="var(--rule)" />
        {orders.map((o) => (
          <circle
            key={o.order_id}
            cx={pad + ((t(o.date) - t0) / (t1 - t0)) * w}
            cy={28}
            r={3 + 6 * Math.sqrt(o.net_revenue / maxRev)}
            fill="var(--ramp-6)"
            fillOpacity={0.7}
          >
            <title>
              {fmt.day(o.date)}: {fmt.money(o.net_revenue, true)}
              {o.category ? `, ${o.category}` : ""}
            </title>
          </circle>
        ))}
        <text x={pad} y={52} fontSize={11} fill="var(--graphite)">
          {fmt.day(orders[0]!.date)}
        </text>
        <text x={width - pad} y={52} fontSize={11} textAnchor="end" fill="var(--graphite)">
          {fmt.day(c.last_order_date)}
        </text>
      </svg>
    </div>
  );
}

function Row({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-rule border-b py-2 last:border-0">
      <dt className="text-graphite">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

/** Side panel: order timeline, RFM, P(alive) and the predicted range. Emails masked for viewers. */
export function CustomerPanel({ customerKey, onClose }: { customerKey: string | null; onClose: () => void }) {
  const { apiUrl, getToken, version } = useApiContext();
  const { meta } = useDisplay();
  const fmt = useFmt();
  const q = useQuery({
    queryKey: apiKey(version, `/v1/customers/${customerKey}`, {}),
    enabled: Boolean(customerKey),
    queryFn: async () =>
      (await apiGet(
        apiUrl,
        await getToken(),
        `/v1/customers/${encodeURIComponent(customerKey!)}`,
        {},
        "this customer",
      )) as {
        data: CustomerDetail;
      },
  });
  const c = q.data?.data;
  return (
    <Dialog.Root open={Boolean(customerKey)} onOpenChange={(o) => !o && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/10" />
        <Dialog.Content className="fade-in fixed inset-y-0 right-0 z-50 w-full max-w-md overflow-auto border-rule border-l bg-sheet p-6 shadow-pop">
          <div className="mb-4 flex items-start justify-between gap-4">
            <Dialog.Title className="break-all font-semibold text-base">
              {c?.email ?? customerKey}
            </Dialog.Title>
            <Dialog.Close className="rounded-[var(--radius-control)] border border-rule px-2 py-1 text-sm">
              Close
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">Customer detail</Dialog.Description>
          {q.isPending ? <FirstLoad rows={8} /> : null}
          {q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} /> : null}
          {c ? (
            <div className="flex flex-col gap-5 text-sm">
              <Timeline c={c} />
              <dl>
                <Row label="Customer">{c.customer_key}</Row>
                <Row label="First order">
                  {fmt.day(c.first_order_date)}
                  {c.first_product ? (
                    <span className="block text-graphite text-xs">{c.first_product}</span>
                  ) : null}
                </Row>
                <Row label="Acquired">
                  {c.channel}, {c.country}
                </Row>
                <Row label="Orders">{fmt.count(c.orders)}</Row>
                <Row label={<Term id="net_revenue">Net revenue</Term>}>{fmt.money(c.net_revenue, true)}</Row>
                <Row label="Last order">
                  {fmt.day(c.last_order_date)} ({fmt.days(c.days_since_last)} ago)
                </Row>
                <Row label={<Term id="rfm_segment">Segment</Term>}>
                  {c.segment}
                  <span className="block text-graphite text-xs">
                    R{c.r} F{c.f} M{c.m}
                  </span>
                </Row>
                <Row label={<Term id="lapse_rate">Stopped buying</Term>}>{c.is_lapsed ? "Yes" : "No"}</Row>
                <Row label={<Term id="p_alive">P(alive)</Term>}>
                  {c.p_alive == null ? "–" : fmt.pct(c.p_alive, 0)}
                  {c.is_drifting ? <span className="block text-graphite text-xs">Drifting</span> : null}
                </Row>
                {meta.clv_visible ? (
                  <Row label={<Term id="predicted_ltv_12m">Next 12 months</Term>}>
                    {c.pred_ltv_p10 == null
                      ? "–"
                      : `${fmt.money(c.pred_ltv_p10)}–${fmt.money(c.pred_ltv_p90)}`}
                  </Row>
                ) : null}
                <Row label={<Term id="historical_ltv">Revenue in first 365 days</Term>}>
                  {fmt.money(c.ltv_365d)}
                </Row>
              </dl>
              <div>
                <h3 className="mb-2 font-semibold">Orders</h3>
                <ul className="divide-y divide-rule">
                  {[...c.orders_timeline].reverse().map((o) => (
                    <li key={o.order_id} className="flex justify-between gap-4 py-1.5">
                      <span>
                        {fmt.day(o.date)}
                        <span className="block text-graphite text-xs">{o.product ?? o.category}</span>
                      </span>
                      <span className="num">{fmt.money(o.net_revenue, true)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : null}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
