/** Server-side error reporting. Inactive unless SENTRY_DSN is set. */
export async function register() {
  if (!process.env.SENTRY_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  Sentry.init({
    dsn: process.env.SENTRY_DSN,
    release: process.env.GIT_SHA,
    environment: process.env.APP_ENV,
    tracesSampleRate: 0.05,
  });
}

export async function onRequestError(...args: unknown[]) {
  if (!process.env.SENTRY_DSN) return;
  const Sentry = await import("@sentry/nextjs");
  // biome-ignore lint/suspicious/noExplicitAny: forwarded unchanged to Sentry
  (Sentry.captureRequestError as (...a: any[]) => void)(...args);
}
