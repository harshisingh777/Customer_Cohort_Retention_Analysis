"use client";

import Link from "next/link";
import { useDisplay } from "./context";

/** "Data through 4 Oct 2026, refreshed today at 02:10." Stale data is never silent. */
export function DataStamp({ compact = false }: { compact?: boolean }) {
  const { meta, fmt } = useDisplay();
  const fresh = meta.freshness;
  if (!meta.data_through || !meta.published_at) {
    return <p className="text-graphite text-xs">{fresh.message ?? "No data published yet."}</p>;
  }
  return (
    <div className="text-xs">
      <p className="text-graphite">
        Data through {fmt.day(meta.data_through)}
        {compact ? "." : `, refreshed ${fmt.relative(meta.published_at)}.`}
      </p>
      {fresh.state === "stale" && fresh.message ? (
        <p className="mt-1 text-signal">
          {fresh.message.replace(" Details on the Data page.", " ")}
          <Link href="/data" className="underline underline-offset-2">
            Details on the Data page.
          </Link>
        </p>
      ) : null}
    </div>
  );
}
