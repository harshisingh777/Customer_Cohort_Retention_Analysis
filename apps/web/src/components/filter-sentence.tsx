"use client";

import * as Dialog from "@radix-ui/react-dialog";
import * as Popover from "@radix-ui/react-popover";
import { useQueryStates } from "nuqs";
import { useId, useMemo, useState } from "react";
import { activeFilterCount, cohortParsers } from "@/lib/search-params";
import { useDisplay } from "./context";
import { Term } from "./term";

type Mode = "cohorts" | "dims" | "range";

function monthsBetween(min: string | null | undefined, max: string | null | undefined): string[] {
  if (!min || !max) return [];
  const out: string[] = [];
  let [y, m] = min.split("-").map(Number) as [number, number];
  const [ey, em] = max.split("-").map(Number) as [number, number];
  while (y < ey || (y === ey && m <= em)) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m += 1;
    if (m > 12) {
      m = 1;
      y += 1;
    }
  }
  return out;
}

function listPhrase(values: string[], noun: string, all: string, max = 2): string {
  if (!values.length) return all;
  if (values.length <= max) return values.join(" and ");
  return `${values.slice(0, max).join(", ")} and ${values.length - max} more ${noun}`;
}

/** An underlined clause that opens a popover. While open it wears the highlighter. */
function Clause({ label, children, title }: { label: string; title: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={`clause ${open ? "highlight" : ""}`}
          aria-label={`${title}: ${label}`}
        >
          {label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="start"
          sideOffset={8}
          collisionPadding={16}
          className="fade-in z-50 w-[min(340px,calc(100vw-32px))] rounded-[var(--radius-control)] border border-rule bg-sheet p-4 font-ui text-sm shadow-pop"
        >
          <p className="mb-2 font-semibold">{title}</p>
          {children}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

function CheckList({
  options,
  selected,
  onChange,
}: {
  options: string[];
  selected: string[];
  onChange: (v: string[]) => void;
}) {
  const id = useId();
  return (
    <div>
      <div className="max-h-64 overflow-auto pr-1">
        {options.map((o, i) => (
          <label key={o} htmlFor={`${id}-${i}`} className="flex cursor-pointer items-center gap-2 py-1">
            <input
              id={`${id}-${i}`}
              type="checkbox"
              checked={selected.includes(o)}
              onChange={(e) =>
                onChange(e.target.checked ? [...selected, o] : selected.filter((x) => x !== o))
              }
              className="accent-[var(--ink)]"
            />
            <span>{o}</span>
          </label>
        ))}
      </div>
      <button
        type="button"
        onClick={() => onChange([])}
        disabled={!selected.length}
        className="mt-2 text-graphite underline underline-offset-4 disabled:no-underline disabled:opacity-50"
      >
        Show all
      </button>
    </div>
  );
}

function RangeControls({
  months,
  from,
  to,
  onChange,
}: {
  months: string[];
  from: string | null;
  to: string | null;
  onChange: (from: string | null, to: string | null) => void;
}) {
  const { fmt } = useDisplay();
  const id = useId();
  return (
    <div className="grid grid-cols-2 gap-3">
      {(["from", "to"] as const).map((which) => (
        <label key={which} htmlFor={`${id}-${which}`} className="flex flex-col gap-1">
          <span className="text-graphite">{which === "from" ? "First cohort" : "Last cohort"}</span>
          <select
            id={`${id}-${which}`}
            value={(which === "from" ? from : to) ?? ""}
            onChange={(e) =>
              which === "from" ? onChange(e.target.value || null, to) : onChange(from, e.target.value || null)
            }
            className="rounded-[var(--radius-control)] border border-rule bg-sheet px-2 py-1.5"
          >
            <option value="">{which === "from" ? "Earliest" : "Latest"}</option>
            {months.map((m) => (
              <option key={m} value={m}>
                {fmt.month(m)}
              </option>
            ))}
          </select>
        </label>
      ))}
    </div>
  );
}

/**
 * The bold thing is language: filters read as a sentence.
 * "Monthly cohorts acquired Jan 2025 to Sep 2026, from all channels, in all countries,
 *  counting revenue net of refunds."  Under 768 px it collapses to "Filters (3)".
 */
export function FilterSentence({ mode = "dims", note }: { mode?: Mode; note?: React.ReactNode }) {
  const { meta, fmt } = useDisplay();
  const [q, setQ] = useQueryStates(cohortParsers, { history: "push" });
  const months = useMemo(
    () => monthsBetween(meta.bounds.min_month?.slice(0, 7), meta.bounds.max_month?.slice(0, 7)),
    [meta.bounds.min_month, meta.bounds.max_month],
  );
  const dims = meta.dimensions;
  const from = q.from ?? months[0] ?? null;
  const to = q.to ?? months[months.length - 1] ?? null;
  const rangeLabel = from && to ? `acquired ${fmt.month(from)} to ${fmt.month(to)}` : "acquired at any time";
  const showDims = mode !== "range";
  const count = activeFilterCount({ from: q.from, to: q.to, ...(showDims ? q : {}) });

  const granularity = (
    <Clause label={q.granularity === "week" ? "Weekly" : "Monthly"} title="Cohort size">
      <div className="flex flex-col gap-1">
        {(["month", "week"] as const).map((g) => (
          <label key={g} className="flex cursor-pointer items-center gap-2 py-1">
            <input
              type="radio"
              name="granularity"
              checked={q.granularity === g}
              onChange={() => setQ({ granularity: g })}
              className="accent-[var(--ink)]"
            />
            {g === "month" ? "Monthly cohorts" : "Weekly cohorts"}
          </label>
        ))}
      </div>
    </Clause>
  );
  const range = (
    <Clause label={rangeLabel} title="Acquired between">
      <RangeControls months={months} from={q.from} to={q.to} onChange={(f, t) => setQ({ from: f, to: t })} />
    </Clause>
  );
  const channel = (
    <Clause label={`from ${listPhrase(q.channel, "channels", "all channels")}`} title="Acquisition channel">
      <CheckList options={dims.channels} selected={q.channel} onChange={(v) => setQ({ channel: v })} />
    </Clause>
  );
  const country = (
    <Clause
      label={`in ${listPhrase(q.country, "countries", "all countries")}`}
      title="Country at first order"
    >
      <CheckList options={dims.countries} selected={q.country} onChange={(v) => setQ({ country: v })} />
    </Clause>
  );
  const category = (
    <Clause
      label={
        q.category.length
          ? `whose first order was in ${listPhrase(q.category, "categories", "")}`
          : "with any first purchase"
      }
      title="Category of the first order"
    >
      <CheckList options={dims.categories} selected={q.category} onChange={(v) => setQ({ category: v })} />
    </Clause>
  );

  const sentence = (
    <p className="serif text-ink text-lg leading-relaxed sm:text-xl">
      {mode === "cohorts" ? (
        <>
          {granularity} cohorts {range}
        </>
      ) : (
        <>Customers {range}</>
      )}
      {showDims ? (
        <>
          , {channel}, {country}, {category}
        </>
      ) : null}
      , counting <Term id="net_revenue">revenue net of refunds</Term>.
    </p>
  );

  return (
    <>
      <div className="hidden md:block">
        {sentence}
        {note ? <p className="mt-1 text-graphite text-sm">{note}</p> : null}
      </div>
      <div className="md:hidden">
        <Dialog.Root>
          <Dialog.Trigger asChild>
            <button
              type="button"
              className="rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-2"
            >
              Filters{count ? ` (${count})` : ""}
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20" />
            <Dialog.Content className="fixed inset-x-4 top-16 z-50 max-h-[80dvh] overflow-auto rounded-[var(--radius-sheet)] border border-rule bg-sheet p-4 shadow-pop">
              <Dialog.Title className="mb-3 font-semibold">Filters</Dialog.Title>
              <div className="flex flex-col gap-5">
                {mode === "cohorts" ? (
                  <Toggle2 value={q.granularity} onChange={(g) => setQ({ granularity: g })} />
                ) : null}
                <RangeControls
                  months={months}
                  from={q.from}
                  to={q.to}
                  onChange={(f, t) => setQ({ from: f, to: t })}
                />
                {showDims ? (
                  <>
                    <fieldset>
                      <legend className="mb-1 text-graphite">Acquisition channel</legend>
                      <CheckList
                        options={dims.channels}
                        selected={q.channel}
                        onChange={(v) => setQ({ channel: v })}
                      />
                    </fieldset>
                    <fieldset>
                      <legend className="mb-1 text-graphite">Country at first order</legend>
                      <CheckList
                        options={dims.countries}
                        selected={q.country}
                        onChange={(v) => setQ({ country: v })}
                      />
                    </fieldset>
                    <fieldset>
                      <legend className="mb-1 text-graphite">Category of the first order</legend>
                      <CheckList
                        options={dims.categories}
                        selected={q.category}
                        onChange={(v) => setQ({ category: v })}
                      />
                    </fieldset>
                  </>
                ) : null}
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="mt-5 w-full rounded-[var(--radius-control)] bg-ink py-2 text-sheet"
                >
                  Show results
                </button>
              </Dialog.Close>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
        {note ? <p className="mt-2 text-graphite text-sm">{note}</p> : null}
      </div>
    </>
  );
}

function Toggle2({ value, onChange }: { value: "month" | "week"; onChange: (v: "month" | "week") => void }) {
  return (
    <fieldset>
      <legend className="mb-1 text-graphite">Cohort size</legend>
      <div className="flex gap-4">
        {(["month", "week"] as const).map((g) => (
          <label key={g} className="flex items-center gap-2">
            <input
              type="radio"
              checked={value === g}
              onChange={() => onChange(g)}
              className="accent-[var(--ink)]"
            />
            {g === "month" ? "Monthly" : "Weekly"}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
