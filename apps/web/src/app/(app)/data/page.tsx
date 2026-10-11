import { HydrationBoundary } from "@tanstack/react-query";
import { DataHealthView } from "@/components/views/data-view";
import { getMeta } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Data" };

export default async function Page() {
  const meta = await getMeta();
  const state = await prefetch(meta.data_version, [{ path: "/v1/data-health", query: {} }]);
  return (
    <HydrationBoundary state={state}>
      <DataHealthView />
    </HydrationBoundary>
  );
}
