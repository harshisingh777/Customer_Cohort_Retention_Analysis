import { getMeta, getMetrics } from "@/lib/server/api";

export const metadata = { title: "Methodology" };

const UNIT: Record<string, string> = {
  percent: "Percent",
  count: "Count",
  currency: "Money",
  days: "Days",
  months: "Months",
  ratio: "Ratio",
  probability: "Probability",
  category: "Category",
  flag: "Yes or no",
};

/** Rendered from metrics.yml through /v1/metrics: the same definitions the pipeline uses. */
export default async function Methodology() {
  const [doc, meta] = await Promise.all([getMetrics(), getMeta()]);
  const s = doc.settings;
  const lapse = doc.lapse_threshold as Record<string, number | null> | null;
  const settings: [string, string][] = [
    ["Reporting timezone", s.reporting_tz],
    ["Reporting currency", s.reporting_currency],
    ["Qualifying order statuses", s.qualifying_statuses.join(", ")],
    [
      "Lapse threshold",
      lapse?.lapse_threshold_days
        ? `${lapse.lapse_threshold_days} days${lapse.override_threshold_days ? " (set by an admin)" : `, from the 90th percentile of ${lapse.gap_count ?? 0} gaps between orders`}`
        : "Not computed yet",
    ],
    [
      "Gross margin (assumption)",
      s.gross_margin != null ? `${Math.round(s.gross_margin * 100)}%` : "Not set; payback is hidden",
    ],
    [
      "Data cutoff",
      s.as_of_date ? `Fixed at ${s.as_of_date} (historical dataset)` : "Yesterday, in the reporting timezone",
    ],
  ];
  return (
    <article className="text-base">
      <header className="mb-8">
        <h1 className="serif font-semibold text-2xl">Methodology</h1>
        <p className="serif measure mt-3 text-graphite">
          Every number in {meta.store_name}'s dashboard is defined once, here. The same definitions drive the
          data pipeline, the API and the definition behind each underlined term.
        </p>
      </header>
      <div className="flex flex-col gap-6">
        <section aria-labelledby="settings-h" className="rounded-[var(--radius-sheet)] bg-sheet p-6">
          <h2 id="settings-h" className="mb-3 font-semibold text-lg">
            Current settings
          </h2>
          <dl className="measure">
            {settings.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-6 border-rule border-b py-2 last:border-0">
                <dt className="text-graphite">{k}</dt>
                <dd className="text-right">{v}</dd>
              </div>
            ))}
          </dl>
        </section>
        <section aria-labelledby="rules-h" className="rounded-[var(--radius-sheet)] bg-sheet p-6">
          <h2 id="rules-h" className="mb-3 font-semibold text-lg">
            Rules that apply everywhere
          </h2>
          <div className="measure flex flex-col gap-4 leading-relaxed">
            {Object.entries(doc.rules).map(([id, text]) => (
              <p key={id} id={id}>
                {text}
              </p>
            ))}
          </div>
        </section>
        <section aria-labelledby="metrics-h" className="rounded-[var(--radius-sheet)] bg-sheet p-6">
          <h2 id="metrics-h" className="mb-3 font-semibold text-lg">
            Metrics
          </h2>
          <div className="measure flex flex-col">
            {doc.metrics.map((m) => (
              <section
                key={m.id}
                id={m.id}
                aria-labelledby={`${m.id}-h`}
                className="scroll-mt-6 border-rule border-b py-5 last:border-0"
              >
                <h3 id={`${m.id}-h`} className="serif font-semibold text-lg">
                  {m.label}
                </h3>
                <p className="mt-2 leading-relaxed">{m.definition}</p>
                <dl className="mt-3 grid grid-cols-[110px_1fr] gap-x-4 gap-y-1 text-sm">
                  <dt className="text-graphite">Formula</dt>
                  <dd>{m.formula}</dd>
                  <dt className="text-graphite">Unit</dt>
                  <dd>{UNIT[m.unit] ?? m.unit}</dd>
                  <dt className="text-graphite">Built in</dt>
                  <dd>{m.model}</dd>
                </dl>
                {m.caveats.length ? (
                  <ul className="mt-3 list-disc space-y-1 pl-5 text-graphite text-sm">
                    {m.caveats.map((c) => (
                      <li key={c}>{c}</li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ))}
          </div>
        </section>
      </div>
    </article>
  );
}
