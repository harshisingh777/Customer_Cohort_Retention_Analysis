/** The web server's only database access: role web_auth (auth.* and read-only ops.users). */
import { Pool } from "pg";
import { env } from "./env";

const globalForPool = globalThis as unknown as { __pool?: Pool };

export const pool: Pool =
  globalForPool.__pool ??
  new Pool({ connectionString: env.webDatabaseUrl, max: 5, idleTimeoutMillis: 30_000 });
if (process.env.NODE_ENV !== "production") globalForPool.__pool = pool;

export type AllowedUser = { email: string; role: "admin" | "viewer"; disabled: boolean };

export async function lookupUser(email: string | null | undefined): Promise<AllowedUser | null> {
  if (!email) return null;
  const { rows } = await pool.query<AllowedUser>(
    "select email, role, disabled from ops.users where email = $1",
    [email.trim().toLowerCase()],
  );
  return rows[0] ?? null;
}

export async function touchLastSeen(email: string): Promise<void> {
  await pool.query("update ops.users set last_seen_at = now() where email = $1", [email]);
}

/** One-time print tokens: the first redemption wins, any replay is refused. */
export async function redeemPrintToken(jti: string): Promise<boolean> {
  const { rowCount } = await pool.query(
    "insert into auth.print_tokens (jti) values ($1) on conflict do nothing",
    [jti],
  );
  return rowCount === 1;
}
