/** Server-only configuration, read at runtime so one image serves every environment. */
export const env = {
  /** API base URL as the web server reaches it (internal network). */
  apiBaseUrl: process.env.API_BASE_URL ?? "http://localhost:8000",
  /** API base URL as the browser reaches it. */
  publicApiUrl: process.env.PUBLIC_API_URL ?? process.env.API_BASE_URL ?? "http://localhost:8000",
  apiJwtSecret: process.env.API_JWT_SECRET ?? "",
  webDatabaseUrl: process.env.WEB_DATABASE_URL ?? "",
  emailServer: process.env.EMAIL_SERVER ?? "",
  emailFrom: process.env.EMAIL_FROM ?? "Retention <no-reply@example.com>",
  googleEnabled: Boolean(process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET),
  /** Local, CI and demo only. Refused when APP_ENV=production. */
  devLogin: process.env.AUTH_DEV_LOGIN === "1" && process.env.APP_ENV !== "production",
  /** A presentation deployment: no email server, so sign-in is the passwordless demo button only. */
  demo: process.env.APP_ENV === "demo",
};
