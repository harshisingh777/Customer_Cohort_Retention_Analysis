import { notFound } from "next/navigation";
import { DisplayProvider } from "@/components/context";
import { type PrintData, PrintDocument } from "@/components/print-document";
import { channelQuery, cohortQuery, repeatQueries, segmentQuery, summaryQueries } from "@/lib/queries";
import { loadCohorts, loadRepeat } from "@/lib/search-params";
import { getMeta, getMetrics, serverGet } from "@/lib/server/api";
import { redeemPrintToken } from "@/lib/server/db";
import { verifyPrintToken } from "@/lib/server/tokens";

export const dynamic = "force-dynamic";
export const metadata = { title: "Print" };

const VIEWS = new Set(["summary", "cohorts", "repeat", "segments", "channels", "data"]);

function describe(sp: Record<string, string | string[] | undefined>): string {
  const parts: string[] = [];
  const list = (k: string) => ([] as string[]).concat(sp[k] ?? []);
  if (sp.from || sp.to) parts.push(`Cohorts ${sp.from ?? "from the start"} to ${sp.to ?? "the latest"}.`);
  for (const [k, label] of [
    ["channel", "Channels"],
    ["country", "Countries"],
    ["category", "First categories"],
  ] as const) {
    if (list(k).length) parts.push(`${label}: ${list(k).join(", ")}.`);
  }
  return parts.length ? parts.join(" ") : "All customers.";
}

/**
 * Rendered by headless Chromium for PDF exports. Access is a one-time print token minted by the
 * worker for the export's owner: verified, then redeemed (replays are refused).
 */
export default async function PrintPage({
  params,
  searchParams,
}: {
  params: Promise<{ view: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { view } = await params;
  const sp = await searchParams;
  if (!VIEWS.has(view)) notFound();
  const token = typeof sp.token === "string" ? sp.token : null;
  const claims = token ? await verifyPrintToken(token) : null;
  if (!token || !claims || !(await redeemPrintToken(claims.jti))) {
    return <p className="p-8">This print link has expired or was already used. Start the export again.</p>;
  }
  const { token: _t, ...rest } = sp;
  const filters = new URLSearchParams();
  for (const [k, v] of Object.entries(rest))
    for (const x of ([] as string[]).concat(v ?? [])) filters.append(k, x);

  const [meta, metrics] = await Promise.all([getMeta(token), getMetrics(token)]);
  const data: PrintData = {};
  if (view === "summary") {
    const { dims, cohorts } = summaryQueries(await loadCohorts(filters));
    [data.summary, data.cohorts] = await Promise.all([
      serverGet("/v1/summary", dims, token),
      serverGet("/v1/cohorts/retention", cohorts, token),
    ]);
  } else if (view === "cohorts") {
    const q = cohortQuery(await loadCohorts(filters));
    [data.cohorts, data.curves] = await Promise.all([
      serverGet("/v1/cohorts/retention", q, token),
      serverGet("/v1/cohorts/curves", q, token),
    ]);
  } else if (view === "repeat") {
    const { dims, firstProduct } = repeatQueries(await loadRepeat(filters));
    [data.timing, data.firstProduct] = await Promise.all([
      serverGet("/v1/repeat/second-order", dims, token),
      serverGet("/v1/repeat/first-product", firstProduct, token),
    ]);
  } else if (view === "segments") {
    data.rfm = await serverGet("/v1/segments/rfm", segmentQuery(await loadCohorts(filters)), token);
  } else if (view === "channels") {
    data.channels = await serverGet("/v1/channels", channelQuery(await loadCohorts(filters)), token);
  } else if (view === "data") {
    data.health = await serverGet("/v1/data-health", {}, token);
  }
  return (
    <DisplayProvider meta={meta} metrics={metrics.metrics} rules={metrics.rules}>
      <PrintDocument view={view} data={data} filters={describe(rest)} />
    </DisplayProvider>
  );
}
