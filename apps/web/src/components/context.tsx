"use client";

/**
 * Two contexts:
 * - Display: formatter, store meta and metric definitions. Everything that renders numbers
 *   reads this, including the print route (which has no live API session).
 * - Api: browser API base URL and a token getter. Only page containers fetch.
 */
import { createContext, useContext, useMemo } from "react";
import type { Meta, MetricDef } from "@/lib/api/types";
import { type Format, makeFormat } from "@/lib/format";

type Display = {
  meta: Meta;
  metrics: Record<string, MetricDef>;
  rules: Record<string, string>;
  fmt: Format;
  isAdmin: boolean;
};

const DisplayContext = createContext<Display | null>(null);

export function DisplayProvider({
  meta,
  metrics,
  rules,
  children,
}: {
  meta: Meta;
  metrics: MetricDef[];
  rules: Record<string, string>;
  children: React.ReactNode;
}) {
  const value = useMemo<Display>(
    () => ({
      meta,
      metrics: Object.fromEntries(metrics.map((m) => [m.id, m])),
      rules,
      fmt: makeFormat({ locale: meta.locale, currency: meta.currency, timezone: meta.timezone }),
      isAdmin: meta.role === "admin",
    }),
    [meta, metrics, rules],
  );
  return <DisplayContext.Provider value={value}>{children}</DisplayContext.Provider>;
}

export function useDisplay(): Display {
  const v = useContext(DisplayContext);
  if (!v) throw new Error("useDisplay outside DisplayProvider");
  return v;
}

export function useFmt(): Format {
  return useDisplay().fmt;
}

type Api = { apiUrl: string; getToken: () => Promise<string>; version: string | null };
export const ApiContext = createContext<Api | null>(null);

export function useApiContext(): Api {
  const v = useContext(ApiContext);
  if (!v) throw new Error("useApiContext outside ApiProvider");
  return v;
}
