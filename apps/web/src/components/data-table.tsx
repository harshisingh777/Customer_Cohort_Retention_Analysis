"use client";

import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useRef } from "react";

const ROW_HEIGHT = 37;

/**
 * Semantic table, virtualised (customer lists run to tens of thousands of rows). Rows are
 * keyboard-activatable; more pages load as the end scrolls into view.
 */
export function DataTable<T>({
  rows,
  columns,
  onRowClick,
  rowLabel,
  hasMore,
  loadMore,
  loadingMore,
  height = 560,
  caption,
}: {
  rows: T[];
  columns: ColumnDef<T, unknown>[];
  onRowClick?: (row: T) => void;
  rowLabel?: (row: T) => string;
  hasMore?: boolean;
  loadMore?: () => void;
  loadingMore?: boolean;
  height?: number;
  caption: string;
}) {
  const table = useReactTable({ data: rows, columns, getCoreRowModel: getCoreRowModel() });
  const scroller = useRef<HTMLDivElement>(null);
  const model = table.getRowModel().rows;
  const virtual = useVirtualizer({
    count: model.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW_HEIGHT,
    overscan: 12,
  });
  const items = virtual.getVirtualItems();
  const last = items[items.length - 1];
  useEffect(() => {
    if (last && hasMore && !loadingMore && last.index >= model.length - 20) loadMore?.();
  }, [last, hasMore, loadingMore, model.length, loadMore]);

  const padTop = items[0]?.start ?? 0;
  const padBottom = virtual.getTotalSize() - (last?.end ?? 0);
  const ncols = columns.length;

  return (
    <div ref={scroller} className="overflow-auto" style={{ maxHeight: height }}>
      <table className="w-full border-separate border-spacing-0 text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead className="sticky top-0 z-10 bg-sheet">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => {
                const align = (h.column.columnDef.meta as { align?: string } | undefined)?.align;
                return (
                  <th
                    key={h.id}
                    scope="col"
                    className={`whitespace-nowrap border-rule border-b px-2 py-2 font-normal text-graphite ${align === "right" ? "text-right" : "text-left"}`}
                  >
                    {flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                );
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {padTop > 0 ? (
            <tr>
              <td colSpan={ncols} style={{ height: padTop }} />
            </tr>
          ) : null}
          {items.map((vi) => {
            const row = model[vi.index]!;
            return (
              <tr
                key={row.id}
                tabIndex={onRowClick ? 0 : undefined}
                aria-label={rowLabel?.(row.original)}
                onClick={() => onRowClick?.(row.original)}
                onKeyDown={(e) => {
                  if ((e.key === "Enter" || e.key === " ") && onRowClick) {
                    e.preventDefault();
                    onRowClick(row.original);
                  }
                }}
                className={onRowClick ? "cursor-pointer hover:bg-ground focus:bg-ground" : ""}
                style={{ height: ROW_HEIGHT }}
              >
                {row.getVisibleCells().map((cell) => {
                  const align = (cell.column.columnDef.meta as { align?: string } | undefined)?.align;
                  return (
                    <td
                      key={cell.id}
                      className={`whitespace-nowrap border-rule border-b px-2 ${align === "right" ? "text-right" : "text-left"}`}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  );
                })}
              </tr>
            );
          })}
          {padBottom > 0 ? (
            <tr>
              <td colSpan={ncols} style={{ height: padBottom }} />
            </tr>
          ) : null}
        </tbody>
      </table>
      {loadingMore ? <p className="py-2 text-center text-graphite text-xs">Loading more customers</p> : null}
    </div>
  );
}
