/** Server-side data access for first paint (Server Components). */
import { redirect } from "next/navigation";
import { cache } from "react";
import { auth } from "@/auth";
import { apiGet } from "@/lib/api/fetcher";
import { ApiError, type Route, type Routes } from "@/lib/api/types";
import { env } from "./env";
import { mintApiToken } from "./tokens";

export type SessionUser = { email: string; role: "admin" | "viewer" };

export const getSessionUser = cache(async (): Promise<SessionUser | null> => {
  const session = await auth();
  if (!session?.user?.email || !session.role) return null;
  return { email: session.user.email, role: session.role };
});

export const requireUser = cache(async (): Promise<SessionUser> => {
  const user = await getSessionUser();
  if (!user) redirect("/sign-in");
  return user;
});

const serverToken = cache(async (): Promise<string> => {
  const user = await requireUser();
  return (await mintApiToken(user.email, user.role)).token;
});

export async function serverGet<R extends Route>(
  path: R,
  query: Record<string, string | string[]> = {},
  token?: string,
): Promise<Routes[R]> {
  return apiGet(env.apiBaseUrl, token ?? (await serverToken()), path, query, "data", {
    cache: "no-store",
  }) as Promise<Routes[R]>;
}

export const getMeta = cache(async (token?: string) => {
  try {
    return await serverGet("/v1/meta", {}, token);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 403))
      redirect("/sign-in?error=AccessDenied");
    throw e;
  }
});

export const getMetrics = cache(async (token?: string) => serverGet("/v1/metrics", {}, token));
