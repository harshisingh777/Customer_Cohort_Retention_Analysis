/** Data surfaces: `sheet` on `ground`, 6 px radius, no shadow, no nested cards. */
export function Sheet({
  children,
  className = "",
  labelledBy,
  id,
}: {
  children: React.ReactNode;
  className?: string;
  labelledBy?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      aria-labelledby={labelledBy}
      className={`sheet relative rounded-[var(--radius-sheet)] bg-sheet p-4 sm:p-6 ${className}`}
    >
      {children}
    </section>
  );
}

export function SheetHeader({
  title,
  id,
  children,
  description,
}: {
  title: React.ReactNode;
  id?: string;
  children?: React.ReactNode;
  description?: React.ReactNode;
}) {
  return (
    <header className="mb-4 flex flex-wrap items-start justify-between gap-3 border-rule border-b pb-3">
      <div className="min-w-0">
        <h2 id={id} className="font-semibold text-base text-ink">
          {title}
        </h2>
        {description ? <p className="mt-1 text-graphite text-sm">{description}</p> : null}
      </div>
      {children ? <div className="no-print flex flex-wrap items-center gap-2">{children}</div> : null}
    </header>
  );
}
