import { NextResponse } from "next/server";
import { getSessionUser } from "@/lib/server/api";
import { mintApiToken } from "@/lib/server/tokens";

export const dynamic = "force-dynamic";

/** Same-origin route: exchanges the session for a 5-minute API token. */
export async function GET() {
  const user = await getSessionUser();
  if (!user) return NextResponse.json({ detail: "Sign in to continue." }, { status: 401 });
  const minted = await mintApiToken(user.email, user.role);
  return NextResponse.json(minted, { headers: { "Cache-Control": "no-store" } });
}
