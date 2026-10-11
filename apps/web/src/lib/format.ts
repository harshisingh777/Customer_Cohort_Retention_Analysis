/**
 * The one formatter (spec §10). Locale and currency come from /v1/meta; dates render in the
 * store's reporting timezone. Rates change in points, counts and money in percent.
 */
export type FormatContext = { locale: string; currency: string; timezone: string };

const DASH = "–";

function plural(n: number, one: string, many: string): string {
  return Math.abs(n) === 1 ? one : many;
}

/** Calendar dates from the API ("2026-10-04") carry no timezone: format them as-is. */
function parseDay(iso: string): Date {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1));
}

export function makeFormat({ locale, currency, timezone }: FormatContext) {
  const int = new Intl.NumberFormat(locale, { maximumFractionDigits: 0 });
  const dec = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  const money0 = new Intl.NumberFormat(locale, { style: "currency", currency, maximumFractionDigits: 0 });
  const money2 = new Intl.NumberFormat(locale, {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const pctFmt = (digits: number) =>
    new Intl.NumberFormat(locale, {
      style: "percent",
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  const day = new Intl.DateTimeFormat(locale, {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  const month = new Intl.DateTimeFormat(locale, { month: "short", year: "numeric", timeZone: "UTC" });
  const monthLong = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" });
  const tzDay = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  const tzTime = new Intl.DateTimeFormat(locale, {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const tzDateTime = new Intl.DateTimeFormat(locale, {
    timeZone: timezone,
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return {
    count: (v: number | null | undefined) => (v == null ? DASH : int.format(v)),
    number: (v: number | null | undefined) => (v == null ? DASH : dec.format(v)),
    /** A rate in [0, 1] as a percent. */
    pct: (v: number | null | undefined, digits = 1) => (v == null ? DASH : pctFmt(digits).format(v)),
    /** Short cell format: one decimal under 10%, none above. */
    pctCell: (v: number | null | undefined) => (v == null ? "" : pctFmt(v < 0.1 && v > 0 ? 1 : 0).format(v)),
    /** Change between two rates, in percentage points. */
    pts: (v: number | null | undefined) =>
      v == null
        ? DASH
        : `${v > 0 ? "+" : v < 0 ? "−" : ""}${dec.format(Math.abs(v))} ${plural(v, "pt", "pts")}`,
    /** Change between two counts or amounts, in percent. */
    pctChange: (v: number | null | undefined) =>
      v == null ? DASH : `${v > 0 ? "+" : v < 0 ? "−" : ""}${dec.format(Math.abs(v))}%`,
    money: (v: number | null | undefined, cents = false) =>
      v == null ? DASH : (cents || Math.abs(v) < 10 ? money2 : money0).format(v),
    ratio: (v: number | null | undefined) => (v == null ? DASH : `${dec.format(v)}×`),
    days: (v: number | null | undefined) =>
      v == null ? DASH : `${int.format(v)} ${plural(v, "day", "days")}`,
    day: (iso: string | null | undefined) => (iso ? day.format(parseDay(iso)) : DASH),
    month: (iso: string | null | undefined) =>
      iso ? month.format(parseDay(iso.length === 7 ? `${iso}-01` : iso)) : DASH,
    monthLong: (iso: string) => monthLong.format(parseDay(iso.length === 7 ? `${iso}-01` : iso)),
    /** Cohort label: "Sep 2026" for months, "3 Mar 2025" for weeks. */
    cohort: (iso: string) =>
      iso.length === 7 ? month.format(parseDay(`${iso}-01`)) : day.format(parseDay(iso)),
    dateTime: (ts: string | null | undefined) => (ts ? tzDateTime.format(new Date(ts)) : DASH),
    /** "today at 02:10", "yesterday at 02:10" or "3 Oct at 02:10", in the reporting timezone. */
    relative: (ts: string, now: Date = new Date()) => {
      const d = new Date(ts);
      const a = tzDay.format(d);
      const today = tzDay.format(now);
      const yesterday = tzDay.format(new Date(now.getTime() - 86_400_000));
      const time = tzTime.format(d);
      if (a === today) return `today at ${time}`;
      if (a === yesterday) return `yesterday at ${time}`;
      return `${day.format(parseDay(a))} at ${time}`;
    },
  };
}

export type Format = ReturnType<typeof makeFormat>;
