import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "@/lib/api/fetcher";
import { ApiError } from "@/lib/api/types";

const ok = () => new Response(JSON.stringify({ data: 1 }), { status: 200 });
const status = (code: number, headers: Record<string, string> = {}) =>
  new Response("", { status: code, headers });

type Reply = Response | Error;

/** Data requests and /healthz checks answer from separate queues; empty queues answer 200. */
function stubFetch(data: Reply[], health: Reply[] = []) {
  const calls = { data: 0, health: 0 };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const isHealth = url.endsWith("/healthz");
      calls[isHealth ? "health" : "data"] += 1;
      const next = (isHealth ? health : data).shift();
      if (next instanceof Error) throw next;
      return next ?? ok();
    }),
  );
  return calls;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("apiGet while the API wakes up", () => {
  it("waits for the API after 429, 502-504 or a dropped connection, then retries", async () => {
    vi.useFakeTimers();
    const calls = stubFetch([status(429), new TypeError("fetch failed"), status(503)]);
    const result = apiGet("https://a1", "t", "/v1/meta");
    await vi.runAllTimersAsync();
    await expect(result).resolves.toEqual({ data: 1 });
    expect(calls.data).toBe(4);
  });

  it("shares one health check between every request waiting on a sleeping API", async () => {
    vi.useFakeTimers();
    const calls = stubFetch(
      Array.from({ length: 5 }, () => status(502)),
      [status(502), status(502)],
    );
    const results = Array.from({ length: 5 }, () => apiGet("https://a2", "t", "/v1/meta"));
    await vi.runAllTimersAsync();
    await expect(Promise.all(results)).resolves.toHaveLength(5);
    expect(calls.health).toBe(3);
    expect(calls.data).toBe(10);
  });

  it("waits at least as long as Retry-After asks", async () => {
    vi.useFakeTimers();
    const calls = stubFetch([status(429, { "Retry-After": "6" })]);
    const result = apiGet("https://a3", "t", "/v1/meta");
    await vi.advanceTimersByTimeAsync(5_000);
    expect(calls.health).toBe(0);
    await vi.runAllTimersAsync();
    await expect(result).resolves.toEqual({ data: 1 });
  });

  it("does not wait on other errors", async () => {
    const calls = stubFetch([status(404)]);
    await expect(apiGet("https://a4", "t", "/v1/meta")).rejects.toMatchObject({ status: 404 });
    expect(calls).toEqual({ data: 1, health: 0 });
  });

  it("gives up at the deadline with the last error, without a burst of requests", async () => {
    vi.useFakeTimers();
    const asleep = () => Array.from({ length: 100 }, () => status(502));
    const calls = stubFetch(asleep(), asleep());
    const result = apiGet("https://a5", "t", "/v1/meta");
    const settled = expect(result).rejects.toBeInstanceOf(ApiError);
    await vi.runAllTimersAsync();
    await settled;
    expect(calls.data + calls.health).toBeLessThan(20);
  });

  it("stops waiting when the caller aborts", async () => {
    vi.useFakeTimers();
    const asleep = () => Array.from({ length: 100 }, () => status(502));
    const calls = stubFetch(asleep(), asleep());
    const controller = new AbortController();
    const result = apiGet("https://a6", "t", "/v1/meta", {}, "data", { signal: controller.signal });
    const settled = expect(result).rejects.toBeDefined();
    await vi.advanceTimersByTimeAsync(1_000);
    controller.abort();
    await settled;
    expect(calls.data).toBe(1);
  });
});
