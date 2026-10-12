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

/** A sleeping API (free hosting) answers 502-504 or nothing until it has woken, which takes up
 * to a minute; GETs are retried until then. Each attempt still has its own TIMEOUT_MS. */
export const WAKE_MS = 90_000;
const RETRY_STATUSES = new Set([502, 503, 504]);
const RETRY_DELAY_MS = 3_000;

function wait(ms: number, signal?: AbortSignal | null): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(signal.reason);
    const t = setTimeout(resolve, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(t);
        reject(signal.reason);
      },
      { once: true },
    );
  });
}

export async function apiGet<R extends Route | `/v1/customers/${string}`>(
  baseUrl: string,
  token: string,
  path: R,
  query: Record<string, string | string[]> = {},
  what = "data",
  init: RequestInit = {},
  wakeMs = WAKE_MS,
): Promise<R extends Route ? Routes[R] : unknown> {
  const deadline = Date.now() + wakeMs;
  const outer = init.signal ?? null;
  for (;;) {
    let res: Response | null = null;
    let failure: ApiError;
    try {
      res = await fetch(`${baseUrl}${path}${toSearch(query)}`, {
        ...init,
        headers: { Authorization: `Bearer ${token}`, Accept: "application/json", ...(init.headers ?? {}) },
        signal: outer
          ? AbortSignal.any([outer, AbortSignal.timeout(TIMEOUT_MS)])
          : AbortSignal.timeout(TIMEOUT_MS),
      });
      if (res.ok) return res.json();
      failure = await problem(res, what);
    } catch (e) {
      if (outer?.aborted) throw e;
      const timedOut = e instanceof DOMException && (e.name === "TimeoutError" || e.name === "AbortError");
      failure = new ApiError(
        0,
        timedOut
          ? `Couldn't load ${what}: the server didn't respond within 10 seconds. Retry.`
          : `Couldn't load ${what}: the server can't be reached. Check your connection and retry.`,
      );
    }
    const retryable = res === null || RETRY_STATUSES.has(res.status);
    if (!retryable || Date.now() + RETRY_DELAY_MS >= deadline) throw failure;
    await wait(RETRY_DELAY_MS, outer);
  }
}
