import { HydrationBoundary } from "@tanstack/react-query";
import type { SearchParams } from "nuqs/server";
import { CohortsView } from "@/components/views/cohorts-view";
import { cohortQuery } from "@/lib/queries";
import { loadCohorts } from "@/lib/search-params";
import { getMeta } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Cohorts" };

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [f, meta] = await Promise.all([loadCohorts(searchParams), getMeta()]);
  const query = cohortQuery(f);
  const state = await prefetch(meta.data_version, [
    { path: "/v1/cohorts/retention", query },
    { path: "/v1/cohorts/curves", query },
  ]);
  return (
    <HydrationBoundary state={state}>
      <CohortsView />
    </HydrationBoundary>
  );
}
