import { describe, expect, it } from "vitest";
import { cohortQuery, customerQuery, summaryQueries } from "@/lib/queries";
import { activeFilterCount, apiQuery, loadCohorts } from "@/lib/search-params";

describe("URL state → API query", () => {
  it("drops empties, sorts arrays and keys, so server and client keys match", () => {
    const q = apiQuery({ to: "2025-06", from: null, channel: ["Email", "Paid search"], country: [] }, [
      "from",
      "to",
      "channel",
      "country",
    ]);
    expect(q).toEqual({ channel: ["Email", "Paid search"], to: "2025-06" });
    expect(Object.keys(q)).toEqual(["channel", "to"]);
  });

  it("parses repeated keys the way the API expects", async () => {
    const f = await loadCohorts(new URLSearchParams("channel=Email&channel=Paid%20search&measure=revenue"));
    expect(f.channel).toEqual(["Email", "Paid search"]);
    expect(cohortQuery(f)).toEqual({
      channel: ["Email", "Paid search"],
      granularity: "month",
      measure: "revenue",
    });
  });

  it("falls back to defaults for invalid literals", async () => {
    const f = await loadCohorts(new URLSearchParams("measure=bogus&granularity=year"));
    expect(f.measure).toBe("customers");
    expect(f.granularity).toBe("month");
  });

  it("builds page queries", () => {
    expect(summaryQueries({ from: "2025-01" }).cohorts).toEqual({
      from: "2025-01",
      granularity: "month",
      measure: "customers",
    });
    expect(customerQuery({ state: "lapsed", sort: "value" })).toEqual({
      limit: "200",
      sort: "value",
      state: "lapsed",
    });
  });

  it("counts active filters for the mobile button", () => {
    expect(activeFilterCount({ from: "2025-01", channel: ["Email"], country: [] })).toBe(2);
  });
});
