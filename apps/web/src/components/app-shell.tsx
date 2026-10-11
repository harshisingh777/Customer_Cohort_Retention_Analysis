"use client";

import { Suspense } from "react";
import { DataStamp } from "./data-stamp";
import { NavRail } from "./nav-rail";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto flex min-h-dvh max-w-[1440px] flex-col md:flex-row">
      <Suspense>
        <NavRail />
      </Suspense>
      <main id="main" className="min-w-0 flex-1 px-4 py-4 sm:px-6 md:py-6">
        {children}
      </main>
    </div>
  );
}

/**
 * The top of every page: a sentence saying what the numbers mean, the filter sentence,
 * and the data stamp.
 */
export function PageHeader({
  title,
  lede,
  filters,
  actions,
}: {
  title: string;
  lede: React.ReactNode;
  filters?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="serif font-semibold text-2xl text-ink">{title}</h1>
        <div className="no-print flex items-center gap-2">{actions}</div>
      </div>
      <p className="serif measure text-base text-graphite">{lede}</p>
      {filters ? <Suspense>{filters}</Suspense> : null}
      <div className="md:hidden">
        <DataStamp />
      </div>
    </header>
  );
}
