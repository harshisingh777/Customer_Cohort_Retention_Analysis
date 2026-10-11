/**
 * Short-lived API tokens. The web server signs a 5-minute JWT (sub, role, exp) with a key shared
 * only with the API; the API verifies every request and enforces roles itself.
 */
import { jwtVerify, SignJWT } from "jose";
import { env } from "./env";

export const TOKEN_TTL_SECONDS = 300;

function key(): Uint8Array {
  if (!env.apiJwtSecret) throw new Error("API_JWT_SECRET is not set");
  return new TextEncoder().encode(env.apiJwtSecret);
}

export async function mintApiToken(
  email: string,
  role: string,
): Promise<{ token: string; expiresAt: number }> {
  const now = Math.floor(Date.now() / 1000);
  const token = await new SignJWT({ role })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(email)
    .setIssuedAt(now)
    .setExpirationTime(now + TOKEN_TTL_SECONDS)
    .sign(key());
  return { token, expiresAt: (now + TOKEN_TTL_SECONDS) * 1000 };
}

export async function verifyPrintToken(token: string): Promise<{ email: string; jti: string } | null> {
  try {
    const { payload } = await jwtVerify(token, key(), { algorithms: ["HS256"] });
    if (payload.scope !== "print" || typeof payload.sub !== "string" || typeof payload.jti !== "string")
      return null;
    return { email: payload.sub, jti: payload.jti };
  } catch {
    return null;
  }
}
