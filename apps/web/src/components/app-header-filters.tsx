"use client";

import { FilterSentence } from "./filter-sentence";

export function AppHeaderFilters({
  mode = "dims",
  note,
}: {
  mode?: "cohorts" | "dims" | "range";
  note?: React.ReactNode;
}) {
  return <FilterSentence mode={mode} note={note} />;
}
