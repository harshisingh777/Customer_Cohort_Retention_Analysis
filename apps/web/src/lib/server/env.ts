/** Server-only configuration, read at runtime so one image serves every environment. */

/** A URL as pasted into a hosting dashboard, without whitespace, quotes, Neon's `psql '...'`
 * wrapper, a whole `NAME=value` line, or a trailing slash. Empty means unset. */
const PASTED_PREFIX = /^(?:psql\s+|[A-Z][A-Z0-9_]*=)/;

function pastedUrl(value: string | undefined): string | undefined {
  let v = (value ?? "").trim();
  while (PASTED_PREFIX.test(v)) v = v.replace(PASTED_PREFIX, "").trim();
  v = v
    .replace(/^['"]+|['"]+$/g, "")
    .trim()
    .replace(/\/+$/, "");
  return v || undefined;
}

const apiBaseUrl = pastedUrl(process.env.API_BASE_URL);

export const env = {
  /** API base URL as the web server reaches it (internal network). */
  apiBaseUrl: apiBaseUrl ?? "http://localhost:8000",
  /** API base URL as the browser reaches it. */
  publicApiUrl: pastedUrl(process.env.PUBLIC_API_URL) ?? apiBaseUrl ?? "http://localhost:8000",
  apiJwtSecret: process.env.API_JWT_SECRET ?? "",
  webDatabaseUrl: pastedUrl(process.env.WEB_DATABASE_URL) ?? "",
  emailServer: process.env.EMAIL_SERVER ?? "",
  emailFrom: process.env.EMAIL_FROM ?? "Retention <no-reply@example.com>",
  googleEnabled: Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET),
  /** Local, CI and demo only. Refused when APP_ENV=production. */
  devLogin: process.env.AUTH_DEV_LOGIN === "1" && process.env.APP_ENV !== "production",
  /** A presentation deployment: no email server, so sign-in is the passwordless demo button only. */
  demo: process.env.APP_ENV === "demo",
};
