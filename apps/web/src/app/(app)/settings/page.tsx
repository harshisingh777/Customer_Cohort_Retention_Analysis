import { HydrationBoundary } from "@tanstack/react-query";
import { notFound } from "next/navigation";
import { SettingsView } from "@/components/views/settings-view";
import { getMeta, requireUser } from "@/lib/server/api";
import { prefetch } from "@/lib/server/prefetch";

export const metadata = { title: "Settings" };

export default async function Page() {
  const user = await requireUser();
  // The API refuses non-admins anyway; this only avoids rendering a page they can't use.
  if (user.role !== "admin") notFound();
  const meta = await getMeta();
  const state = await prefetch(meta.data_version, [
    { path: "/v1/settings", query: {} },
    { path: "/v1/users", query: {} },
  ]);
  return (
    <HydrationBoundary state={state}>
      <SettingsView />
    </HydrationBoundary>
  );
}
