"use client";

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const detail =
    error.message && !error.message.startsWith("An error occurred")
      ? error.message
      : "Couldn't load this page: the data service didn't answer. Retry in a moment.";
  return (
    <div role="alert" className="mx-auto max-w-xl px-4 py-16">
      <h1 className="serif font-semibold text-xl">This page didn't load</h1>
      <p className="mt-3 text-signal">{detail}</p>
      <button
        type="button"
        onClick={reset}
        className="mt-6 rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-1.5 hover:border-ink"
      >
        Retry
      </button>
    </div>
  );
}
