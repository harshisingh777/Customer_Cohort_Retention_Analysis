/**
 * Every filter lives in the URL (spec §10). One set of parsers serves the server loader, the
 * client hooks and the API query, so a shared link reproduces the exact view. Literal values
 * mirror the API's OpenAPI enums (see schema.d.ts); arrays are repeated keys, as the API expects.
 */
import {
  createLoader,
  parseAsInteger,
  parseAsNativeArrayOf,
  parseAsString,
  parseAsStringLiteral,
} from "nuqs/server";
import type { components } from "@/lib/api/schema";

type S = components["schemas"];
export const GRANULARITIES = ["month", "week"] as const satisfies readonly S["CohortTable"]["granularity"][];
export const MEASURES = [
  "customers",
  "revenue",
  "cumulative",
] as const satisfies readonly S["CohortTable"]["measure"][];
export const LEVELS = ["category", "product"] as const satisfies readonly S["FirstProduct"]["level"][];
export const STATES = ["all", "active", "lapsed", "drifting"] as const;
export const SORTS = ["value", "recent", "orders", "risk"] as const;

export const dimParsers = {
  from: parseAsString,
  to: parseAsString,
  channel: parseAsNativeArrayOf(parseAsString),
  country: parseAsNativeArrayOf(parseAsString),
  category: parseAsNativeArrayOf(parseAsString),
};

export const cohortParsers = {
  ...dimParsers,
  granularity: parseAsStringLiteral(GRANULARITIES).withDefault("month"),
  measure: parseAsStringLiteral(MEASURES).withDefault("customers"),
  select: parseAsString,
  pin: parseAsNativeArrayOf(parseAsString),
};

export const repeatParsers = {
  ...dimParsers,
  level: parseAsStringLiteral(LEVELS).withDefault("category"),
  highlight: parseAsString,
};

export const customerParsers = {
  ...dimParsers,
  segment: parseAsString,
  state: parseAsStringLiteral(STATES).withDefault("all"),
  sort: parseAsStringLiteral(SORTS).withDefault("value"),
  customer: parseAsString,
};

export const channelParsers = { from: parseAsString, to: parseAsString };
export const pageParsers = { limit: parseAsInteger };

export const loadDims = createLoader(dimParsers);
export const loadCohorts = createLoader(cohortParsers);
export const loadRepeat = createLoader(repeatParsers);
export const loadCustomers = createLoader(customerParsers);
export const loadChannels = createLoader(channelParsers);

export type DimFilters = {
  from: string | null;
  to: string | null;
  channel: string[];
  country: string[];
  category: string[];
};

export type Query = Record<string, string | number | string[] | null | undefined>;

/** Only the keys the API accepts, without empties, in a stable order (part of the cache key). */
export function apiQuery(values: Query, keys: readonly string[]): Record<string, string | string[]> {
  const out: Record<string, string | string[]> = {};
  for (const k of [...keys].sort()) {
    const v = values[k];
    if (v === null || v === undefined || v === "") continue;
    if (Array.isArray(v)) {
      if (v.length) out[k] = [...v].sort();
    } else out[k] = String(v);
  }
  return out;
}

export const DIM_KEYS = ["from", "to", "channel", "country", "category"] as const;

export function activeFilterCount(f: Partial<DimFilters>): number {
  return (
    (f.from || f.to ? 1 : 0) +
    (f.channel?.length ? 1 : 0) +
    (f.country?.length ? 1 : 0) +
    (f.category?.length ? 1 : 0)
  );
}
