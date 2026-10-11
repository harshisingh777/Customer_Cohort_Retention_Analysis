"use client";

import * as Popover from "@radix-ui/react-popover";
import Link from "next/link";
import { useState } from "react";
import { useDisplay } from "./context";

/**
 * Every metric name is a Term: dotted underline, opens its definition from metrics.yml.
 * `children` is the merchant's words ("bought again"); the precise name is one hover away.
 */
export function Term({ id, children }: { id: string; children?: React.ReactNode }) {
  const { metrics } = useDisplay();
  const [open, setOpen] = useState(false);
  const m = metrics[id];
  if (!m) return <>{children}</>;
  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          type="button"
          className={`term text-left ${open ? "highlight" : ""}`}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          aria-label={`${typeof children === "string" ? children : m.label}: definition`}
        >
          {children ?? m.label}
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          side="bottom"
          align="start"
          sideOffset={6}
          collisionPadding={16}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          className="fade-in z-50 w-[min(360px,calc(100vw-32px))] rounded-[var(--radius-control)] border border-rule bg-sheet p-4 text-sm shadow-pop"
        >
          <p className="font-semibold">{m.label}</p>
          <p className="mt-1">{m.definition}</p>
          <p className="mt-2 text-graphite">{m.formula}</p>
          {m.caveats.length ? (
            <ul className="mt-2 list-disc space-y-1 pl-4 text-graphite">
              {m.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          ) : null}
          <Link href={`/methodology#${m.id}`} className="mt-3 inline-block underline underline-offset-4">
            Methodology
          </Link>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
