/**
 * Auth.js v5: invite-only. Magic link (and Google when configured); a passwordless dev sign-in
 * exists only when AUTH_DEV_LOGIN=1 outside production. The session lives in the web app; the
 * API never trusts it directly, only the short-lived tokens minted from it.
 */
import PostgresAdapter from "@auth/pg-adapter";
import NextAuth from "next-auth";
import type { Provider } from "next-auth/providers";
import Credentials from "next-auth/providers/credentials";
import Google from "next-auth/providers/google";
import Nodemailer from "next-auth/providers/nodemailer";
import { lookupUser, pool, touchLastSeen } from "@/lib/server/db";
import { env } from "@/lib/server/env";

const ROLE_RECHECK_MS = 5 * 60_000;

const providers: Provider[] = [
  Nodemailer({
    server: env.emailServer || "smtp://localhost:25",
    from: env.emailFrom,
    ...(env.emailServer
      ? {}
      : {
          // Local development: no SMTP. The link is printed to the web server log.
          async sendVerificationRequest({ identifier, url }: { identifier: string; url: string }) {
            console.info(JSON.stringify({ level: "info", msg: "magic link", email: identifier, url }));
          },
        }),
  }),
];
if (env.googleEnabled) providers.push(Google);
if (env.devLogin) {
  providers.push(
    Credentials({
      id: "dev",
      name: "Development sign-in",
      credentials: { email: { label: "Email", type: "email" } },
      async authorize(credentials) {
        const email = String(credentials?.email ?? "")
          .trim()
          .toLowerCase();
        const user = await lookupUser(email);
        return user && !user.disabled ? { id: email, email } : null;
      },
    }),
  );
}

declare module "next-auth" {
  interface Session {
    role: "admin" | "viewer" | null;
  }
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  adapter: PostgresAdapter(pool),
  session: { strategy: "jwt", maxAge: 8 * 60 * 60 },
  pages: { signIn: "/sign-in", verifyRequest: "/sign-in?sent=1", error: "/sign-in" },
  trustHost: true,
  providers,
  callbacks: {
    // Invite-only: an email not on ops.users never gets a session.
    async signIn({ user }) {
      const allowed = await lookupUser(user.email);
      return Boolean(allowed && !allowed.disabled);
    },
    async jwt({ token, user }) {
      if (user?.email) token.email = user.email.toLowerCase();
      const checkedAt = (token.roleCheckedAt as number | undefined) ?? 0;
      if (Date.now() - checkedAt > ROLE_RECHECK_MS) {
        const allowed = await lookupUser(token.email);
        token.role = allowed && !allowed.disabled ? allowed.role : null;
        token.roleCheckedAt = Date.now();
        if (allowed) await touchLastSeen(allowed.email).catch(() => undefined);
      }
      return token;
    },
    async session({ session, token }) {
      if (token.email) session.user.email = token.email;
      session.role = (token.role as "admin" | "viewer" | null) ?? null;
      return session;
    },
  },
});

export const providerFlags = {
  google: env.googleEnabled,
  dev: env.devLogin,
  demo: env.demo && env.devLogin,
  emailServer: Boolean(env.emailServer),
};
