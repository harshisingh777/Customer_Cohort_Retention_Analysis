import { describe, expect, it } from "vitest";
import { contrast, GRAPHITE, INK, makeRamp, RAMP, type Step, stepColor, textOnStep, WHITE } from "@/lib/ramp";

const AA = 4.5;

describe("retention ramp", () => {
  it("has seven steps, light to dark", () => {
    expect(RAMP).toHaveLength(7);
    const lum = RAMP.map((h) => contrast(h, "#000000"));
    for (let i = 1; i < lum.length; i++) expect(lum[i]!).toBeLessThan(lum[i - 1]!);
  });

  it.each([1, 2, 3, 4, 5, 6, 7] as Step[])("cell text on step %i meets WCAG AA", (step) => {
    const ratio = contrast(stepColor(step), textOnStep(step));
    expect(ratio).toBeGreaterThanOrEqual(AA);
  });

  it("flips text from ink to white at step 5", () => {
    expect(textOnStep(4)).toBe(INK);
    expect(textOnStep(5)).toBe(WHITE);
  });

  it("muted small-sample text (graphite on sheet) meets AA", () => {
    expect(contrast(GRAPHITE, "#FFFFFF")).toBeGreaterThanOrEqual(AA);
  });

  it("maps observed zero to the lightest step and the max to the darkest", () => {
    const ramp = makeRamp(0.4);
    expect(ramp(0)).toBe(1);
    expect(ramp(0.4)).toBe(7);
    expect(ramp(0.2)).toBe(4);
  });

  it("handles an all-zero table", () => {
    expect(makeRamp(0)(0)).toBe(1);
  });
});
