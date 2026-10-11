/**
 * The single sequential hue that encodes data (spec §8.2). No green/amber/red: it fails
 * colour-blind users and turns a measurement into a judgement. Cell text flips from ink to
 * white at step 5; every step's contrast is checked in tests/unit/ramp.test.ts.
 */
import { scaleQuantize } from "d3-scale";

export const RAMP = ["#F1F5FA", "#D6E3F0", "#B0C8E1", "#82A7CC", "#4A79A8", "#2F6296", "#17406E"] as const;
export const INK = "#18222D";
export const WHITE = "#FFFFFF";
export const GRAPHITE = "#5A6672";

export type Step = 1 | 2 | 3 | 4 | 5 | 6 | 7;

/** Quantize [0, max] into seven steps. An observed zero is step 1 (lightest), never blank. */
export function makeRamp(max: number) {
  const scale = scaleQuantize<number>()
    .domain([0, max > 0 ? max : 1])
    .range([1, 2, 3, 4, 5, 6, 7]);
  return (value: number): Step => (value <= 0 ? 1 : (scale(value) as Step));
}

export function stepColor(step: Step): string {
  return RAMP[step - 1]!;
}

export function textOnStep(step: Step): string {
  return step >= 5 ? WHITE : INK;
}

// WCAG 2.x relative luminance and contrast ratio.
function channel(c: number): number {
  const s = c / 255;
  return s <= 0.04045 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

export function luminance(hex: string): number {
  const h = hex.replace("#", "");
  const [r, g, b] = [0, 2, 4].map((i) => channel(Number.parseInt(h.slice(i, i + 2), 16)));
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi! + 0.05) / (lo! + 0.05);
}
