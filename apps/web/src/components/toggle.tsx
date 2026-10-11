"use client";

import * as ToggleGroup from "@radix-ui/react-toggle-group";

/** Segmented choice for sheet headers (granularity, measure, level). */
export function Toggle<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <ToggleGroup.Root
      type="single"
      value={value}
      onValueChange={(v) => v && onChange(v as T)}
      aria-label={label}
      className="inline-flex rounded-[var(--radius-control)] border border-rule p-0.5"
    >
      {options.map((o) => (
        <ToggleGroup.Item
          key={o.value}
          value={o.value}
          className="rounded-[3px] px-2.5 py-1 text-graphite text-sm data-[state=on]:bg-ground data-[state=on]:font-medium data-[state=on]:text-ink"
        >
          {o.label}
        </ToggleGroup.Item>
      ))}
    </ToggleGroup.Root>
  );
}
