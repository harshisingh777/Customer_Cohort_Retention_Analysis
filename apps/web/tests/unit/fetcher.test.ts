import { afterEach, describe, expect, it, vi } from "vitest";
import { apiGet } from "@/lib/api/fetcher";
import { ApiError } from "@/lib/api/types";

const ok = () => new Response(JSON.stringify({ data: 1 }), { status: 200 });
const status = (code: number) => new Response("", { status: code });

function stubFetch(...responses: (Response | Error)[]) {
  const fetchMock = vi.fn(async () => {
    const next = responses.shift();
    if (next instanceof Error) throw next;
    return next ?? ok();
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("apiGet while the API wakes up", () => {
  it("retries 502-504 and dropped connections until the API answers", async () => {
    vi.useFakeTimers();
    const fetchMock = stubFetch(status(502), new TypeError("fetch failed"), status(503), ok());
    const result = apiGet("https://api", "t", "/v1/meta");
    await vi.runAllTimersAsync();
    await expect(result).resolves.toEqual({ data: 1 });
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("does not retry other errors", async () => {
    const fetchMock = stubFetch(status(404));
    await expect(apiGet("https://api", "t", "/v1/meta")).rejects.toMatchObject({ status: 404 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("gives up at the wake deadline with the last error", async () => {
    vi.useFakeTimers();
    stubFetch(...Array.from({ length: 50 }, () => status(502)));
    const result = apiGet("https://api", "t", "/v1/meta", {}, "data", {}, 10_000);
    const settled = expect(result).rejects.toBeInstanceOf(ApiError);
    await vi.runAllTimersAsync();
    await settled;
  });

  it("stops retrying when the caller aborts", async () => {
    vi.useFakeTimers();
    const fetchMock = stubFetch(...Array.from({ length: 50 }, () => status(502)));
    const controller = new AbortController();
    const result = apiGet("https://api", "t", "/v1/meta", {}, "data", { signal: controller.signal });
    const settled = expect(result).rejects.toBeDefined();
    await vi.advanceTimersByTimeAsync(4_000);
    controller.abort();
    await settled;
    expect(fetchMock.mock.calls.length).toBeLessThan(4);
  });
});
