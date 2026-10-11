"use client";

import Link from "next/link";
import type { Finding } from "@/lib/api/types";
import { EmptyState } from "./states";

/** Up to three sentences, in serif, each linking to the view that proves it. */
export function Findings({ findings, emptyText }: { findings: Finding[]; emptyText?: string }) {
  if (!findings.length) {
    return (
      <EmptyState>
        {emptyText ??
          "Nothing stands out: every recent cohort is within the normal range of the six before it, and no first purchase differs clearly from the store average."}
      </EmptyState>
    );
  }
  return (
    <ul className="flex flex-col gap-4">
      {findings.map((f) => (
        <li key={f.id} className="serif measure text-base text-ink leading-relaxed sm:text-lg">
          <Link href={f.href} className="decoration-rule underline-offset-4 hover:underline">
            {f.text}
          </Link>
        </li>
      ))}
    </ul>
  );
}
