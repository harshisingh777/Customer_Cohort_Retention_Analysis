import { HydrationBoundary } from "@tanstack/react-query";
import type { SearchParams } from "nuqs/server";
import { RepeatView } from "@/components/views/repeat-view";
import { repeatQueries } from "@/lib/queries";
import { loadRepeat } from "@/lib/search-params";
import { getMeta } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Repeat" };

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [f, meta] = await Promise.all([loadRepeat(searchParams), getMeta()]);
  const { dims, firstProduct } = repeatQueries(f);
  const state = await prefetch(meta.data_version, [
    { path: "/v1/repeat/second-order", query: dims },
    { path: "/v1/repeat/first-product", query: firstProduct },
  ]);
  return (
    <HydrationBoundary state={state}>
      <RepeatView />
    </HydrationBoundary>
  );
}
