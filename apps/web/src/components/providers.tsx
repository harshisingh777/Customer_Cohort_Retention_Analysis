"use client";

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { NuqsAdapter } from "nuqs/adapters/next/app";
import { useCallback, useMemo, useRef, useState } from "react";
import { apiGet } from "@/lib/api/fetcher";
import { ApiError, type Meta, type MetricDef } from "@/lib/api/types";
import { ApiContext, DisplayProvider } from "./context";
import { ToastProvider } from "./toast";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // Aligned with the API's Cache-Control max-age.
        staleTime: 60_000,
        gcTime: 10 * 60_000,
        refetchOnWindowFocus: false,
        retry: (count, error) =>
          error instanceof ApiError && error.status >= 400 && error.status < 500 ? false : count < 2,
      },
    },
  });
}

function useTokenGetter(): () => Promise<string> {
  const current = useRef<{ token: string; expiresAt: number } | null>(null);
  const inflight = useRef<Promise<string> | null>(null);
  return useCallback(async () => {
    const t = current.current;
    // Refresh 30 s before expiry so no request ever goes out with a dead token.
    if (t && t.expiresAt - Date.now() > 30_000) return t.token;
    if (!inflight.current) {
      inflight.current = fetch("/api/token", { cache: "no-store" })
        .then(async (res) => {
          if (res.status === 401) {
            window.location.href = "/sign-in";
            throw new ApiError(401, "Your session ended. Sign in again.");
          }
          if (!res.ok) throw new ApiError(res.status, "Couldn't start an API session. Reload the page.");
          const body = (await res.json()) as { token: string; expiresAt: number };
          current.current = body;
          return body.token;
        })
        .finally(() => {
          inflight.current = null;
        });
    }
    return inflight.current;
  }, []);
}

function Live({
  apiUrl,
  initialMeta,
  metrics,
  rules,
  children,
}: {
  apiUrl: string;
  initialMeta: Meta;
  metrics: MetricDef[];
  rules: Record<string, string>;
  children: React.ReactNode;
}) {
  const getToken = useTokenGetter();
  // A new publish changes data_version, which is part of every query key: everything refetches once.
  const meta = useQuery({
    queryKey: ["meta"],
    queryFn: async () => apiGet(apiUrl, await getToken(), "/v1/meta", {}, "store details"),
    initialData: initialMeta,
    refetchInterval: 60_000,
  }).data;
  const api = useMemo(
    () => ({ apiUrl, getToken, version: meta.data_version }),
    [apiUrl, getToken, meta.data_version],
  );
  return (
    <ApiContext.Provider value={api}>
      <DisplayProvider meta={meta} metrics={metrics} rules={rules}>
        {children}
      </DisplayProvider>
    </ApiContext.Provider>
  );
}

export function Providers(props: {
  apiUrl: string;
  initialMeta: Meta;
  metrics: MetricDef[];
  rules: Record<string, string>;
  children: React.ReactNode;
}) {
  const [client] = useState(makeQueryClient);
  return (
    <QueryClientProvider client={client}>
      <NuqsAdapter>
        <ToastProvider>
          <Live {...props} />
        </ToastProvider>
      </NuqsAdapter>
    </QueryClientProvider>
  );
}
