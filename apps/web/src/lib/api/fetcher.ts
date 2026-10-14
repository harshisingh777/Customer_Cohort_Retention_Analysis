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

/** A sleeping API (free hosting) holds requests, or its edge answers 429 or 502-504, until it has
 * woken (up to a minute). Requests don't retry on their own: that burst is what an edge throttles.
 * One shared health check per base URL (per server process or browser tab) waits for the API with
 * growing gaps, and the waiting requests then try again. Only GETs come through here. */
export const WAKE_MS = 90_000;
const WAIT_STATUSES = new Set([429, 502, 503, 504]);
const FIRST_GAP_MS = 2_000;
const MAX_GAP_MS = 15_000;
const PROBE_TIMEOUT_MS = 60_000;

const waking = new Map<string, Promise<boolean>>();

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

function abortable<T>(p: Promise<T>, signal: AbortSignal | null): Promise<T> {
  if (!signal) return p;
  return Promise.race([p, wait(2 ** 31 - 1, signal).then(() => p)]);
}

function retryAfterMs(res: Response | null): number {
  const v = res?.headers.get("retry-after");
  if (!v) return 0;
  const seconds = Number(v);
  if (Number.isFinite(seconds)) return seconds * 1000;
  const at = Date.parse(v);
  return Number.isNaN(at) ? 0 : at - Date.now();
}

/** True once the API's /healthz answers; false if the deadline comes first. Joins a check already
 * running for the same API. */
function untilAwake(baseUrl: string, deadline: number, firstGapMs: number): Promise<boolean> {
  const running = waking.get(baseUrl);
  if (running) return running;
  const check = (async () => {
    let gap = Math.min(Math.max(firstGapMs, FIRST_GAP_MS), MAX_GAP_MS);
    while (Date.now() + gap < deadline) {
      await wait(gap);
      let res: Response | null = null;
      try {
        // A long timeout: a waking API holds this one request rather than receiving many.
        const timeout = Math.max(1, Math.min(PROBE_TIMEOUT_MS, deadline - Date.now()));
        res = await fetch(`${baseUrl}/healthz`, { cache: "no-store", signal: AbortSignal.timeout(timeout) });
        if (res.ok) return true;
      } catch {
        /* still asleep or unreachable */
      }
      gap = Math.min(Math.max(retryAfterMs(res), gap * 2), MAX_GAP_MS);
    }
    return false;
  })().finally(() => waking.delete(baseUrl));
  waking.set(baseUrl, check);
  return check;
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
  for (let attempt = 0; ; attempt++) {
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
    const waitable = res === null || WAIT_STATUSES.has(res.status);
    if (!waitable || Date.now() >= deadline) throw failure;
    const gap = Math.max(retryAfterMs(res), FIRST_GAP_MS * 2 ** attempt);
    if (!(await abortable(untilAwake(baseUrl, deadline, gap), outer))) throw failure;
  }
}
