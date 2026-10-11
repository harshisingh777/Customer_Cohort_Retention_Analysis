import { signOut } from "@/auth";

export const metadata = { title: "Sign out" };

async function doSignOut() {
  "use server";
  await signOut({ redirectTo: "/sign-in" });
}

export default function SignOut() {
  return (
    <main className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-4">
      <h1 className="serif font-semibold text-2xl">Sign out?</h1>
      <form action={doSignOut} className="mt-6">
        <button
          type="submit"
          className="rounded-[var(--radius-control)] bg-ink px-4 py-2 font-medium text-sheet"
        >
          Sign out
        </button>
      </form>
    </main>
  );
}
