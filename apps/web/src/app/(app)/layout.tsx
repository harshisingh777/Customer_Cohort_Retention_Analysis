import { AppShell } from "@/components/app-shell";
import { Providers } from "@/components/providers";
import { getMeta, getMetrics, requireUser } from "@/lib/server/api";
import { env } from "@/lib/server/env";

export const dynamic = "force-dynamic";

/**
 * Authenticated shell. The session check here only decides what to render; the API enforces
 * access on every request with its own token verification and role checks.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  await requireUser();
  const [meta, metrics] = await Promise.all([getMeta(), getMetrics()]);
  return (
    <Providers apiUrl={env.publicApiUrl} initialMeta={meta} metrics={metrics.metrics} rules={metrics.rules}>
      <a
        href="#main"
        className="sr-only z-50 rounded-[var(--radius-control)] bg-sheet px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <AppShell>{children}</AppShell>
    </Providers>
  );
}
