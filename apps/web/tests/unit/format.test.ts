import { describe, expect, it } from "vitest";
import { makeFormat } from "@/lib/format";

const fmt = makeFormat({ locale: "en-GB", currency: "GBP", timezone: "Europe/London" });

describe("format", () => {
  it("formats rates as percentages", () => {
    expect(fmt.pct(0.264)).toBe("26.4%");
    expect(fmt.pct(null)).toBe("–");
    expect(fmt.pctCell(0.264)).toBe("26%");
    expect(fmt.pctCell(0.034)).toBe("3.4%");
    expect(fmt.pctCell(0)).toBe("0%");
  });

  it("changes in rates are points, changes in amounts are percent", () => {
    expect(fmt.pts(-2)).toBe("−2 pts");
    expect(fmt.pts(1)).toBe("+1 pt");
    expect(fmt.pctChange(4)).toBe("+4%");
    expect(fmt.pctChange(-8.2)).toBe("−8.2%");
  });

  it("formats money in the store currency", () => {
    expect(fmt.money(84)).toBe("£84");
    expect(fmt.money(1234.5)).toBe("£1,235");
    expect(fmt.money(1234.5, true)).toBe("£1,234.50");
    expect(fmt.money(4.95)).toBe("£4.95");
  });

  it("formats calendar dates without shifting them", () => {
    expect(fmt.day("2026-10-04")).toBe("4 Oct 2026");
    expect(fmt.month("2026-03")).toBe("Mar 2026");
    expect(fmt.cohort("2025-03-03")).toBe("3 Mar 2025");
  });

  it("describes refresh time relative to today in the store timezone", () => {
    const now = new Date("2026-10-05T12:00:00Z");
    expect(fmt.relative("2026-10-05T01:10:00Z", now)).toBe("today at 02:10");
    expect(fmt.relative("2026-10-04T01:10:00Z", now)).toBe("yesterday at 02:10");
  });

  it("uses plain counts and day units", () => {
    expect(fmt.count(1204)).toBe("1,204");
    expect(fmt.days(1)).toBe("1 day");
    expect(fmt.days(34)).toBe("34 days");
  });
});
