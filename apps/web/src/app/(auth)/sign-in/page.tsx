import { redirect } from "next/navigation";
import { AuthError } from "next-auth";
import { providerFlags, signIn } from "@/auth";
import { getSessionUser } from "@/lib/server/api";

export const metadata = { title: "Sign in" };
export const dynamic = "force-dynamic";

const ERRORS: Record<string, string> = {
  AccessDenied: "This email isn't invited. Ask an admin for access.",
  Verification: "That sign-in link has expired or was already used. Ask for a new one.",
  CredentialsSignin: "This email isn't invited. Ask an admin for access.",
  Default: "Sign-in didn't work. Try again.",
};

async function emailSignIn(formData: FormData) {
  "use server";
  try {
    await signIn("nodemailer", { email: String(formData.get("email") ?? ""), redirectTo: "/summary" });
  } catch (e) {
    if (e instanceof AuthError)
      redirect(`/sign-in?error=${e.type === "AccessDenied" ? "AccessDenied" : "Default"}`);
    throw e;
  }
}

async function googleSignIn() {
  "use server";
  await signIn("google", { redirectTo: "/summary" });
}

async function devSignIn(formData: FormData) {
  "use server";
  try {
    await signIn("dev", { email: String(formData.get("email") ?? ""), redirectTo: "/summary" });
  } catch (e) {
    if (e instanceof AuthError) redirect("/sign-in?error=CredentialsSignin");
    throw e;
  }
}

const input = "w-full rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-2";
const primary = "w-full rounded-[var(--radius-control)] bg-ink px-3 py-2 font-medium text-sheet";
const secondary =
  "w-full rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-2 hover:border-ink";

export default async function SignIn({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  if (await getSessionUser()) redirect("/summary");
  const sp = await searchParams;
  const error = sp.error ? (ERRORS[sp.error] ?? ERRORS.Default) : null;
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-4 py-12">
      <h1 className="serif font-semibold text-2xl">Sign in</h1>
      <p className="serif mt-2 text-graphite">Retention and cohort analytics. Access is by invitation.</p>
      {error ? (
        <p role="alert" className="mt-6 text-signal">
          {error}
        </p>
      ) : null}
      {sp.sent ? (
        <p role="status" className="mt-6">
          Check your email: a sign-in link is on its way.
          {!providerFlags.emailServer
            ? " (Local development: the link is printed in the web server log.)"
            : ""}
        </p>
      ) : null}
      <div className="mt-8 flex flex-col gap-6 rounded-[var(--radius-sheet)] bg-sheet p-6">
        <form action={emailSignIn} className="flex flex-col gap-3">
          <label htmlFor="email" className="text-graphite">
            Work email
          </label>
          <input id="email" name="email" type="email" required autoComplete="email" className={input} />
          <button type="submit" className={primary}>
            Email me a sign-in link
          </button>
        </form>
        {providerFlags.google ? (
          <form action={googleSignIn}>
            <button type="submit" className={secondary}>
              Continue with Google
            </button>
          </form>
        ) : null}
        {providerFlags.dev ? (
          <form action={devSignIn} className="flex flex-col gap-3 border-rule border-t pt-6">
            <label htmlFor="dev-email" className="text-graphite">
              Development sign-in (local and CI only)
            </label>
            <input
              id="dev-email"
              name="email"
              type="email"
              required
              defaultValue="admin@example.com"
              className={input}
            />
            <button type="submit" className={secondary}>
              Sign in without a link
            </button>
          </form>
        ) : null}
      </div>
    </main>
  );
}
