/** Query keys shared by server prefetch and client hooks. They must match exactly. */
export function apiKey(version: string | null, path: string, query: Record<string, string | string[]>) {
  return ["api", version, path, query] as const;
}

/** Paged lists use their own key space (different cache shape from single queries). */
export function infiniteKey(version: string | null, path: string, query: Record<string, string | string[]>) {
  return ["api-pages", version, path, query] as const;
}
