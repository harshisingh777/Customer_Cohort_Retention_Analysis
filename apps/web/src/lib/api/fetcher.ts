/** Isomorphic GET used by both the server (first paint) and the browser (TanStack Query). */
import { ApiError, type Route, type Routes } from "./types";

export const TIMEOUT_MS = 10_000;

export function toSearch(query: Record<string, string | string[]>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) {
    if (Array.isArray(v)) for (const x of v) sp.append(k, x);
    else sp.append(k, v);
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

export async function problem(res: Response, what: string): Promise<ApiError> {
  let detail = `Couldn't load ${what}: the server answered ${res.status}. Retry.`;
  let requestId: string | null = res.headers.get("x-request-id");
  let type: string | null = null;
  try {
    const body = await res.json();
    if (body?.detail) detail = body.detail;
    requestId = body?.request_id ?? requestId;
    type = body?.type ?? null;
  } catch {
    /* not problem+json */
  }
  return new ApiError(res.status, detail, requestId, type);
}

export async function apiGet<R extends Route | `/v1/customers/${string}`>(
  baseUrl: string,
  token: string,
  path: R,
  query: Record<string, string | string[]> = {},
  what = "data",
  init: RequestInit = {},
): Promise<R extends Route ? Routes[R] : unknown> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl}${path}${toSearch(query)}`, {
      ...init,
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json", ...(init.headers ?? {}) },
      signal: init.signal ?? AbortSignal.timeout(TIMEOUT_MS),
    });
  } catch (e) {
    const timedOut = e instanceof DOMException && (e.name === "TimeoutError" || e.name === "AbortError");
    throw new ApiError(
      0,
      timedOut
        ? `Couldn't load ${what}: the server didn't respond within 10 seconds. Retry.`
        : `Couldn't load ${what}: the server can't be reached. Check your connection and retry.`,
    );
  }
  if (!res.ok) throw await problem(res, what);
  return res.json();
}
