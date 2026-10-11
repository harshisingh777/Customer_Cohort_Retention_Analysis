import { HydrationBoundary } from "@tanstack/react-query";
import type { SearchParams } from "nuqs/server";
import { SummaryView } from "@/components/views/summary-view";
import { summaryQueries } from "@/lib/queries";
import { loadDims } from "@/lib/search-params";
import { getMeta } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Summary" };

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [f, meta] = await Promise.all([loadDims(searchParams), getMeta()]);
  const { dims, cohorts } = summaryQueries(f);
  const state = await prefetch(meta.data_version, [
    { path: "/v1/summary", query: dims },
    { path: "/v1/cohorts/retention", query: cohorts },
  ]);
  return (
    <HydrationBoundary state={state}>
      <SummaryView />
    </HydrationBoundary>
  );
}
