import { HydrationBoundary } from "@tanstack/react-query";
import type { SearchParams } from "nuqs/server";
import { SegmentsView } from "@/components/views/segments-view";
import { segmentQuery } from "@/lib/queries";
import { loadDims } from "@/lib/search-params";
import { getMeta } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Segments" };

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [f, meta] = await Promise.all([loadDims(searchParams), getMeta()]);
  const state = await prefetch(meta.data_version, [{ path: "/v1/segments/rfm", query: segmentQuery(f) }]);
  return (
    <HydrationBoundary state={state}>
      <SegmentsView />
    </HydrationBoundary>
  );
}
