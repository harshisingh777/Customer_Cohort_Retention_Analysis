"use client";

import type { UseQueryResult } from "@tanstack/react-query";
import { Component, type ErrorInfo, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/types";

/** Static blocks in the shape of the final layout. No shimmer (spec §8.6). */
export function FirstLoad({ rows = 6, height = 28 }: { rows?: number; height?: number }) {
  return (
    <div role="status" aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="rounded-[var(--radius-control)] bg-ground" style={{ height }} />
      ))}
    </div>
  );
}

/** A 2 px line at the top of the sheet, only when the wait passes 300 ms. */
export function ProgressLine({ active }: { active: boolean }) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    if (!active) {
      setShow(false);
      return;
    }
    const t = setTimeout(() => setShow(true), 300);
    return () => clearTimeout(t);
  }, [active]);
  if (!show) return null;
  return (
    <div
      role="progressbar"
      aria-label="Loading new numbers"
      className="absolute top-0 right-0 left-0 h-[2px] overflow-hidden rounded-t-[var(--radius-sheet)]"
    >
      <div className="h-full w-full bg-ink" />
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <p className="py-8 text-graphite">{children}</p>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const detail =
    error instanceof ApiError
      ? error.detail
      : "Couldn't show this: something in the page failed to render. Retry.";
  const rid = error instanceof ApiError ? error.requestId : null;
  return (
    <div role="alert" className="py-6">
      <p className="text-signal">{detail}</p>
      <div className="mt-3 flex items-center gap-4">
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="rounded-[var(--radius-control)] border border-rule px-3 py-1.5 hover:border-ink"
          >
            Retry
          </button>
        ) : null}
        {rid ? <span className="text-graphite text-xs">Request {rid}</span> : null}
      </div>
    </div>
  );
}

/**
 * The four states of every data component. While new filter results load, the previous
 * numbers stay visible at reduced opacity, then swap without animation.
 */
export function QueryView<T>({
  query,
  isEmpty,
  empty,
  rows,
  children,
}: {
  query: UseQueryResult<T>;
  isEmpty?: (data: T) => boolean;
  empty?: React.ReactNode;
  rows?: number;
  children: (data: T) => React.ReactNode;
}) {
  if (query.isPending) return <FirstLoad rows={rows} />;
  if (query.isError && (!query.data || !query.isPlaceholderData)) {
    return <ErrorState error={query.error} onRetry={() => query.refetch()} />;
  }
  const data = query.data as T;
  const stale = query.isPlaceholderData;
  return (
    <>
      <ProgressLine active={query.isFetching} />
      <div aria-busy={query.isFetching} style={{ opacity: stale ? 0.5 : 1 }}>
        {isEmpty?.(data)
          ? (empty ?? <EmptyState>Nothing to show for these filters.</EmptyState>)
          : children(data)}
      </div>
    </>
  );
}

/** One boundary per sheet: a failed chart never blanks the page. */
export class SheetBoundary extends Component<{ children: React.ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(
      JSON.stringify({
        level: "error",
        msg: "render error",
        error: error.message,
        stack: info.componentStack,
      }),
    );
  }
  render() {
    if (this.state.error)
      return <ErrorState error={this.state.error} onRetry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}
