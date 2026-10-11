"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useApiContext } from "@/components/context";
import { apiGet, TIMEOUT_MS } from "./fetcher";
import { apiKey } from "./keys";
import type { Route, Routes } from "./types";

/**
 * Every filtered query keeps the previous data on screen while new numbers load
 * (placeholderData: keepPreviousData). The key includes the data version.
 */
export function useApi<R extends Route>(path: R, query: Record<string, string | string[]>, what: string) {
  const { apiUrl, getToken, version } = useApiContext();
  return useQuery<Routes[R]>({
    queryKey: apiKey(version, path, query),
    queryFn: async ({ signal }) =>
      apiGet(apiUrl, await getToken(), path, query, what, {
        signal: AbortSignal.any([signal, AbortSignal.timeout(TIMEOUT_MS)]),
      }) as Promise<Routes[R]>,
    placeholderData: keepPreviousData,
  });
}

/** Authenticated non-GET calls (refresh, settings, exports, users). */
export function useApiMutationFetch() {
  const { apiUrl, getToken } = useApiContext();
  return async (method: string, path: string, body?: unknown): Promise<Response> => {
    const token = await getToken();
    return fetch(`${apiUrl}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(60_000),
    });
  };
}
