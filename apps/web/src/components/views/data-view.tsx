"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { problem } from "@/lib/api/fetcher";
import { useApi, useApiMutationFetch } from "@/lib/api/hooks";
import type { Schemas } from "@/lib/api/types";
import { PageHeader } from "../app-shell";
import { useDisplay } from "../context";
import { ExportButtons } from "../export-buttons";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";
import { useToast } from "../toast";

type Health = Schemas["DataHealth"];
type Q = Record<string, number | string | null>;

function Stat({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-rule border-b py-2 last:border-0">
      <dt className="text-graphite">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}

function RefreshButton() {
  const call = useApiMutationFetch();
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    try {
      const res = await call("POST", "/v1/pipeline/runs");
      if (!res.ok) throw await problem(res, "the refresh");
      const body = (await res.json()) as { job_id: number; existing: boolean };
      toast(body.existing ? "A refresh is already running. Following it." : "Refresh started.");
      for (let i = 0; i < 180; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const s = await call("GET", `/v1/pipeline/runs/${body.job_id}`);
        if (!s.ok) break;
        const job = (await s.json()) as { status: string; error: string | null };
        if (job.status === "succeeded") {
          toast("Refresh published.");
          break;
        }
        if (job.status === "failed") {
          toast("Refresh failed. Yesterday's data stays in place; see the latest run below.", "error");
          break;
        }
      }
      await qc.invalidateQueries();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't start a refresh.", "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <button
      type="button"
      onClick={run}
      disabled={busy}
      className="rounded-[var(--radius-control)] bg-ink px-3 py-1.5 text-sheet text-sm disabled:opacity-60"
    >
      {busy ? "Refreshing" : "Refresh now"}
    </button>
  );
}

export function HealthPanels({ d }: { d: Health }) {
  const { fmt } = useDisplay();
  const q = (d.quality ?? {}) as Q;
  const n = (k: string) => Number(q[k] ?? 0);
  const latest = d.runs.find((r) => r.tests);
  const tests = (latest?.tests ?? {}) as {
    tests_passed?: number;
    tests_warned?: number;
    models?: number;
    failures?: { node: string; message: string }[];
  };
  const recon = d.reconciliation as {
    source_revenue: number;
    mart_revenue: number;
    delta_pct: number;
    unidentified_revenue: number;
  } | null;
  const drops = d.ingest.filter((b) => (b.rows_dropped as number) > 0);
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
      <Sheet labelledBy="fresh-title">
        <SheetHeader title="Freshness" id="fresh-title" />
        <dl>
          <Stat label="Data through">{fmt.day(d.data_through)}</Stat>
          <Stat label="Published">{d.published_at ? fmt.dateTime(d.published_at) : "–"}</Stat>
          <Stat label="Status">
            {d.freshness.state === "fresh" ? (
              "Up to date"
            ) : (
              <span className="text-signal">{d.freshness.message}</span>
            )}
          </Stat>
          <Stat label="Version">
            <span className="text-xs">{d.data_version ?? "–"}</span>
          </Stat>
        </dl>
      </Sheet>
      <Sheet labelledBy="tests-title">
        <SheetHeader
          title="Tests"
          id="tests-title"
          description="dbt tests and invariants run on every refresh; a failure blocks the publish."
        />
        <dl>
          <Stat label="Models built">{fmt.count(tests.models ?? 0)}</Stat>
          <Stat label="Tests passed">{fmt.count(tests.tests_passed ?? 0)}</Stat>
          <Stat label="Warnings">{fmt.count(tests.tests_warned ?? 0)}</Stat>
          <Stat label="Failures">{fmt.count(tests.failures?.length ?? 0)}</Stat>
        </dl>
        {tests.failures?.length ? (
          <ul className="mt-3 space-y-1 text-signal text-xs">
            {tests.failures.map((f) => (
              <li key={f.node}>
                {f.node}: {f.message.slice(0, 200)}
              </li>
            ))}
          </ul>
        ) : null}
      </Sheet>
      <Sheet labelledBy="recon-title">
        <SheetHeader
          title={<Term id="reconciliation">Reconciliation</Term>}
          id="recon-title"
          description="Net revenue in the dashboard against the same revenue recomputed from the source rows, last 90 days. A gap over 0.5% blocks the publish."
        />
        {recon ? (
          <dl>
            <Stat label="Source revenue">{fmt.money(recon.source_revenue, true)}</Stat>
            <Stat label="Dashboard revenue">{fmt.money(recon.mart_revenue, true)}</Stat>
            <Stat label="Difference">{fmt.pct(recon.delta_pct, 2)}</Stat>
            <Stat label="Revenue without a customer">{fmt.money(recon.unidentified_revenue)}</Stat>
          </dl>
        ) : (
          <p className="text-graphite">Appears after the first refresh.</p>
        )}
      </Sheet>
      <Sheet labelledBy="quality-title">
        <SheetHeader title="Customers and identity" id="quality-title" />
        <dl>
          <Stat label="Customers">{fmt.count(n("customers"))}</Stat>
          <Stat label="Qualifying orders">
            {fmt.count(n("orders_qualifying"))} of {fmt.count(n("orders_total"))}
          </Stat>
          <Stat label={<Term id="identity_merge_rate">Guest orders merged</Term>}>
            {q.identity_merge_rate == null ? "No guest orders" : fmt.pct(Number(q.identity_merge_rate))}
          </Stat>
          <Stat label="Orders without a customer">{fmt.count(n("orders_without_identity"))}</Stat>
          <Stat label="Excluded: refunded or zero">{fmt.count(n("orders_refunded_or_zero"))}</Stat>
          <Stat label="Excluded: status or test">
            {fmt.count(n("orders_status_excluded") + n("orders_test"))}
          </Stat>
          <Stat label="Missing exchange rate">{fmt.count(n("orders_missing_fx"))}</Stat>
          <Stat label="New customers with a known channel">
            {fmt.pct(n("customers") ? 1 - n("customers_unattributed") / n("customers") : null, 0)}
          </Stat>
          <Stat label={<Term id="lapse_threshold">Lapse threshold</Term>}>
            {fmt.days(n("lapse_threshold_days"))}
            {q.override_threshold_days ? " (set by an admin)" : ""}
          </Stat>
        </dl>
      </Sheet>
      <Sheet labelledBy="drops-title">
        <SheetHeader
          title="Dropped rows"
          id="drops-title"
          description="Rows left out at ingest and why. Rows without a customer bias retention upward, so they're counted here."
        />
        {drops.length ? (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-rule border-b text-graphite">
                <th scope="col" className="py-2 text-left font-normal">
                  Source
                </th>
                <th scope="col" className="py-2 text-left font-normal">
                  Reason
                </th>
                <th scope="col" className="py-2 text-right font-normal">
                  Rows
                </th>
              </tr>
            </thead>
            <tbody>
              {drops.flatMap((b) =>
                Object.entries((b.drop_reasons ?? {}) as Record<string, number>)
                  .filter(([, v]) => v > 0)
                  .map(([reason, v]) => (
                    <tr
                      key={`${b.source}-${b.entity}-${reason}`}
                      className="border-rule border-b last:border-0"
                    >
                      <td className="py-2">
                        {String(b.source)} {String(b.entity).replace("_", " ")}
                      </td>
                      <td className="py-2">{reason.replaceAll("_", " ")}</td>
                      <td className="py-2 text-right">
                        {fmt.count(v)}
                        <span className="block text-graphite text-xs">
                          {fmt.pct(v / Math.max(1, b.rows_in as number), 0)} of rows
                        </span>
                      </td>
                    </tr>
                  )),
              )}
            </tbody>
          </table>
        ) : (
          <p className="text-graphite">No rows were dropped.</p>
        )}
      </Sheet>
      <Sheet labelledBy="clv-title">
        <SheetHeader
          title={<Term id="predicted_ltv_12m">Prediction check</Term>}
          id="clv-title"
          description="The model is refit weekly, trained on all but the last 180 days, and scored against what customers actually spent in them."
        />
        {d.clv ? (
          <dl>
            <Stat label="Holdout error (MAPE)">
              {d.clv.holdout_mape == null ? "–" : fmt.pct(Number(d.clv.holdout_mape), 0)} (limit 30%)
            </Stat>
            <Stat label="Predictions shown">{d.clv.visible ? "Yes" : "No"}</Stat>
            <Stat label="Fitted">{fmt.dateTime(String(d.clv.fitted_at))}</Stat>
            <Stat label="Model">
              <span className="text-xs">{String(d.clv.model_version)}</span>
            </Stat>
          </dl>
        ) : (
          <p className="text-graphite">The first weekly model fit hasn't run yet.</p>
        )}
      </Sheet>
    </div>
  );
}

export function RunsTable({ d }: { d: Health }) {
  const { fmt } = useDisplay();
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <caption className="sr-only">Last 30 pipeline runs</caption>
        <thead>
          <tr className="border-rule border-b text-graphite">
            <th scope="col" className="py-2 pr-3 text-left font-normal">
              Started
            </th>
            <th scope="col" className="py-2 pr-3 text-left font-normal">
              Job
            </th>
            <th scope="col" className="py-2 pr-3 text-left font-normal">
              Outcome
            </th>
            <th scope="col" className="py-2 pr-3 text-right font-normal">
              Took
            </th>
            <th scope="col" className="py-2 text-left font-normal">
              Steps
            </th>
          </tr>
        </thead>
        <tbody>
          {d.runs.map((r) => (
            <tr key={r.id} className="border-rule border-b align-top last:border-0">
              <td className="py-2 pr-3 whitespace-nowrap">{fmt.dateTime(r.started_at)}</td>
              <td className="py-2 pr-3">
                {r.trigger.split(":")[0]}
                <span className="block text-graphite text-xs">run {r.id}</span>
              </td>
              <td className="py-2 pr-3">
                {r.status === "failed" ? (
                  <span className="text-signal">Failed{r.error ? `: ${r.error.slice(0, 140)}` : ""}</span>
                ) : r.status === "published" ? (
                  "Published"
                ) : (
                  "Running"
                )}
              </td>
              <td className="py-2 pr-3 text-right">
                {r.duration_s == null ? "–" : `${Math.round(r.duration_s)} s`}
              </td>
              <td className="py-2 text-graphite text-xs">
                {(r.steps as { name: string; seconds: number; status: string }[])
                  .map((s) => `${s.name} ${Math.round(s.seconds)}s${s.status === "failed" ? " ✕" : ""}`)
                  .join(" · ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DataHealthView() {
  const { isAdmin } = useDisplay();
  const health = useApi("/v1/data-health", {}, "data health");
  return (
    <>
      <PageHeader
        title="Data"
        lede="Can you trust these numbers? When they were refreshed, whether the checks passed, and how they reconcile with the source."
        actions={
          <>
            <ExportButtons pdfView="data" params={{}} />
            {isAdmin ? <RefreshButton /> : null}
          </>
        }
      />
      <SheetBoundary>
        <QueryView query={health} rows={10}>
          {(d) => (
            <div className="flex flex-col gap-6">
              <HealthPanels d={d} />
              <Sheet labelledBy="runs-title">
                <SheetHeader title="Last 30 runs" id="runs-title" />
                <RunsTable d={d} />
              </Sheet>
            </div>
          )}
        </QueryView>
      </SheetBoundary>
    </>
  );
}
