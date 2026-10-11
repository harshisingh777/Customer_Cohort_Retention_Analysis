import { HydrationBoundary } from "@tanstack/react-query";
import type { SearchParams } from "nuqs/server";
import { CustomersView } from "@/components/views/customers-view";
import { customerQuery } from "@/lib/queries";
import { loadCustomers } from "@/lib/search-params";
import { getMeta } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Customers" };

export default async function Page({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const [f, meta] = await Promise.all([loadCustomers(searchParams), getMeta()]);
  const state = await prefetch(meta.data_version, [
    { path: "/v1/customers", query: customerQuery(f), paged: true },
  ]);
  return (
    <HydrationBoundary state={state}>
      <CustomersView />
    </HydrationBoundary>
  );
}
