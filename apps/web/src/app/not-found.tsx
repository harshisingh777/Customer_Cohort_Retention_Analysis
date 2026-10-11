import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-xl px-4 py-16">
      <h1 className="serif font-semibold text-xl">This page doesn't exist</h1>
      <p className="mt-3 text-graphite">The link may be out of date.</p>
      <Link href="/summary" className="mt-6 inline-block underline underline-offset-4">
        Go to the summary
      </Link>
    </main>
  );
}
