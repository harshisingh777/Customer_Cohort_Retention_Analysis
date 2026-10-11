/** Server-side prefetch into a QueryClient so the client hydrates without a loading flash. */
import { dehydrate, QueryClient } from "@tanstack/react-query";
import { apiKey, infiniteKey } from "@/lib/api/keys";
import type { Route } from "@/lib/api/types";
import { serverGet } from "./api";

type Request = { path: Route; query: Record<string, string | string[]>; paged?: boolean };

export async function prefetch(version: string | null, requests: Request[]) {
  const qc = new QueryClient();
  // prefetch never throws: a failed prefetch leaves the client to retry and show the error state.
  await Promise.all(
    requests.map(({ path, query, paged }) =>
      paged
        ? qc.prefetchInfiniteQuery({
            queryKey: infiniteKey(version, path, query),
            queryFn: () => serverGet(path, query),
            initialPageParam: null as string | null,
          })
        : qc.prefetchQuery({ queryKey: apiKey(version, path, query), queryFn: () => serverGet(path, query) }),
    ),
  );
  return dehydrate(qc);
}
