"use client";

import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";
import type { ColumnDef } from "@tanstack/react-table";
import { useQueryStates } from "nuqs";
import { useMemo } from "react";
import { apiGet } from "@/lib/api/fetcher";
import { infiniteKey } from "@/lib/api/keys";
import type { CustomerRow, Routes } from "@/lib/api/types";
import { customerQuery } from "@/lib/queries";
import { customerParsers, STATES } from "@/lib/search-params";
import { AppHeaderFilters } from "../app-header-filters";
import { PageHeader } from "../app-shell";
import { useApiContext, useDisplay } from "../context";
import { CustomerPanel } from "../customer-panel";
import { DataTable } from "../data-table";
import { ExportButtons } from "../export-buttons";
import { Sheet, SheetHeader } from "../sheet";
import { EmptyState, ErrorState, FirstLoad, ProgressLine } from "../states";
import { Term } from "../term";

const SEGMENTS = [
  "Champions",
  "Loyal",
  "Potential loyalists",
  "New customers",
  "Needs attention",
  "Can't lose them",
  "At risk",
  "Lost",
];
const STATE_LABEL: Record<(typeof STATES)[number], string> = {
  all: "Everyone",
  active: "Still buying",
  lapsed: "Stopped buying",
  drifting: "Drifting",
};
const SORT_LABEL = {
  value: "Highest value",
  recent: "Most recent",
  orders: "Most orders",
  risk: "Most at risk",
} as const;

type Page = Routes["/v1/customers"];

function Select<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T | "";
  options: { value: T | ""; label: string }[];
  onChange: (v: T | "") => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-graphite">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T | "")}
        className="rounded-[var(--radius-control)] border border-rule bg-sheet px-2 py-1"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

/** "No customers match these filters. Remove the country filter to see 1,204 customers." */
function NoMatch({ q, onRemove }: { q: Record<string, string | string[]>; onRemove: (k: string) => void }) {
  const { apiUrl, getToken, version } = useApiContext();
  const { fmt } = useDisplay();
  const removable = ["segment", "state", "country", "category", "channel", "from"].find(
    (k) => q[k] && !(k === "state" && q[k] === "all"),
  );
  const relaxed = useMemo(() => {
    if (!removable) return null;
    const { [removable]: _, ...rest } = q;
    if (removable === "from") delete rest.to;
    return { ...rest, limit: "1" };
  }, [q, removable]);
  const alt = useQuery({
    queryKey: ["api", version, "/v1/customers", relaxed],
    enabled: Boolean(relaxed),
    queryFn: async () =>
      (await apiGet(apiUrl, await getToken(), "/v1/customers", relaxed!, "customers")) as Page,
  });
  const names: Record<string, string> = {
    segment: "segment",
    state: "status",
    country: "country",
    category: "first category",
    channel: "channel",
    from: "date range",
  };
  return (
    <EmptyState>
      No customers match these filters.
      {removable && alt.data?.data.total ? (
        <>
          {" "}
          <button
            type="button"
            onClick={() => onRemove(removable)}
            className="text-ink underline underline-offset-4"
          >
            Remove the {names[removable]} filter to see {fmt.count(alt.data.data.total)} customers.
          </button>
        </>
      ) : null}
    </EmptyState>
  );
}

export function CustomersView() {
  const { apiUrl, getToken, version } = useApiContext();
  const { fmt, meta } = useDisplay();
  const [f, setF] = useQueryStates(customerParsers, { history: "replace" });
  const q = customerQuery(f);
  const pages = useInfiniteQuery({
    queryKey: infiniteKey(version, "/v1/customers", q),
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam, signal }) =>
      (await apiGet(
        apiUrl,
        await getToken(),
        "/v1/customers",
        pageParam ? { ...q, cursor: pageParam } : q,
        "customers",
        { signal },
      )) as Page,
    getNextPageParam: (last) => last.data.next_cursor,
    placeholderData: keepPreviousData,
  });
  const rows = useMemo(() => pages.data?.pages.flatMap((p) => p.data.rows) ?? [], [pages.data]);
  const total = pages.data?.pages[0]?.data.total ?? 0;

  const columns = useMemo<ColumnDef<CustomerRow, unknown>[]>(() => {
    const cols: ColumnDef<CustomerRow, unknown>[] = [
      {
        id: "customer",
        header: "Customer",
        cell: ({ row }) => (
          <span className="block max-w-[220px] truncate">
            {row.original.email ?? row.original.customer_key}
          </span>
        ),
      },
      { id: "segment", header: "Segment", cell: ({ row }) => row.original.segment },
      {
        id: "orders",
        header: "Orders",
        meta: { align: "right" },
        cell: ({ row }) => fmt.count(row.original.orders),
      },
      {
        id: "revenue",
        header: () => <Term id="net_revenue">Net revenue</Term>,
        meta: { align: "right" },
        cell: ({ row }) => fmt.money(row.original.net_revenue),
      },
      { id: "last", header: "Last order", cell: ({ row }) => fmt.day(row.original.last_order_date) },
      {
        id: "status",
        header: () => <Term id="lapse_rate">Status</Term>,
        cell: ({ row }) =>
          row.original.is_lapsed ? "Stopped buying" : row.original.is_drifting ? "Drifting" : "Still buying",
      },
      {
        id: "alive",
        header: () => <Term id="p_alive">P(alive)</Term>,
        meta: { align: "right" },
        cell: ({ row }) => (row.original.p_alive == null ? "–" : fmt.pct(row.original.p_alive, 0)),
      },
    ];
    if (meta.clv_visible) {
      cols.push({
        id: "pred",
        header: () => <Term id="predicted_ltv_12m">Next 12 months</Term>,
        meta: { align: "right" },
        cell: ({ row }) =>
          row.original.pred_ltv_p10 == null
            ? "–"
            : `${fmt.money(row.original.pred_ltv_p10)}–${fmt.money(row.original.pred_ltv_p90)}`,
      });
    }
    cols.push({
      id: "channel",
      header: "Channel",
      cell: ({ row }) => (row.original.channel === "unattributed" ? "Unknown" : row.original.channel),
    });
    return cols;
  }, [fmt, meta.clv_visible]);

  return (
    <>
      <PageHeader
        title="Customers"
        lede="Who your customers are, who's drifting away and who has stopped buying. Open anyone to see their orders."
        filters={<AppHeaderFilters />}
        actions={<ExportButtons csvView="customers" params={q} />}
      />
      <Sheet labelledBy="customers-title">
        <SheetHeader
          title={pages.data ? `${fmt.count(total)} customers` : "Customers"}
          id="customers-title"
          description={
            <>
              <Term id="lapse_rate">Stopped buying</Term> means no order for longer than this store's lapse
              threshold
              {meta.lapse_threshold_days ? ` (${meta.lapse_threshold_days} days)` : ""}. Drifting means{" "}
              <Term id="p_alive">P(alive)</Term> below 50% but not yet past it.
            </>
          }
        >
          <Select
            label="Segment"
            value={(f.segment ?? "") as string}
            onChange={(v) => setF({ segment: v || null })}
            options={[{ value: "", label: "All" }, ...SEGMENTS.map((s) => ({ value: s, label: s }))]}
          />
          <Select
            label="Status"
            value={f.state}
            onChange={(v) => setF({ state: (v || "all") as (typeof STATES)[number] })}
            options={STATES.map((s) => ({ value: s, label: STATE_LABEL[s] }))}
          />
          <Select
            label="Sort"
            value={f.sort}
            onChange={(v) => setF({ sort: (v || "value") as keyof typeof SORT_LABEL })}
            options={(Object.keys(SORT_LABEL) as (keyof typeof SORT_LABEL)[]).map((s) => ({
              value: s,
              label: SORT_LABEL[s],
            }))}
          />
        </SheetHeader>
        {pages.isPending ? (
          <FirstLoad rows={12} />
        ) : pages.isError && !pages.data ? (
          <ErrorState error={pages.error} onRetry={() => pages.refetch()} />
        ) : total === 0 ? (
          <NoMatch
            q={q}
            onRemove={(k) => setF({ [k]: null, ...(k === "from" ? { to: null } : {}) } as never)}
          />
        ) : (
          <>
            <ProgressLine active={pages.isFetching && !pages.isFetchingNextPage} />
            <div style={{ opacity: pages.isPlaceholderData ? 0.5 : 1 }}>
              <DataTable
                rows={rows}
                columns={columns}
                caption="Customers"
                onRowClick={(r) => setF({ customer: r.customer_key })}
                rowLabel={(r) =>
                  `${r.email ?? r.customer_key}, ${r.segment}, ${fmt.money(r.net_revenue)}. Open details.`
                }
                hasMore={pages.hasNextPage}
                loadMore={() => pages.fetchNextPage()}
                loadingMore={pages.isFetchingNextPage}
              />
            </div>
          </>
        )}
      </Sheet>
      <CustomerPanel customerKey={f.customer} onClose={() => setF({ customer: null })} />
    </>
  );
}
