/**
 * Browser error reporting. NEXT_PUBLIC_SENTRY_DSN is inlined at build time: without it the
 * branch is dead code and the Sentry SDK is not shipped at all.
 */
if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
  void import("@sentry/nextjs").then((Sentry) =>
    Sentry.init({ dsn: process.env.NEXT_PUBLIC_SENTRY_DSN, tracesSampleRate: 0.05 }),
  );
}
