"use client";

import * as Dialog from "@radix-ui/react-dialog";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useDisplay } from "./context";
import { DataStamp } from "./data-stamp";

const PRIMARY = [
  { href: "/summary", label: "Summary" },
  { href: "/cohorts", label: "Cohorts" },
  { href: "/repeat", label: "Repeat" },
  { href: "/segments", label: "Segments" },
  { href: "/channels", label: "Channels" },
  { href: "/customers", label: "Customers" },
];
const SECONDARY = [
  { href: "/methodology", label: "Methodology" },
  { href: "/data", label: "Data" },
];
const CARRY = ["from", "to", "channel", "country", "category"];

/** Links keep the shared filters, so moving between pages never loses the view. */
function useHref() {
  const sp = useSearchParams();
  return (href: string, carry = true) => {
    if (!carry) return href;
    const out = new URLSearchParams();
    for (const k of CARRY) for (const v of sp.getAll(k)) out.append(k, v);
    const s = out.toString();
    return s ? `${href}?${s}` : href;
  };
}

function Links({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const href = useHref();
  const { isAdmin } = useDisplay();
  const item = (l: { href: string; label: string }, carry = true) => {
    const active = pathname === l.href || pathname.startsWith(`${l.href}/`);
    return (
      <li key={l.href}>
        <Link
          href={href(l.href, carry)}
          onClick={onNavigate}
          aria-current={active ? "page" : undefined}
          className={`block rounded-[var(--radius-control)] px-2 py-1.5 ${active ? "font-semibold text-ink" : "text-graphite hover:text-ink"}`}
        >
          {active ? <span className="highlight">{l.label}</span> : l.label}
        </Link>
      </li>
    );
  };
  return (
    <>
      <ul className="flex flex-col gap-0.5">{PRIMARY.map((l) => item(l))}</ul>
      <ul className="mt-6 flex flex-col gap-0.5">
        {SECONDARY.map((l) => item(l, false))}
        {isAdmin ? item({ href: "/settings", label: "Settings" }, false) : null}
      </ul>
    </>
  );
}

function Account() {
  const { meta } = useDisplay();
  return (
    <div className="text-xs">
      <p className="truncate text-graphite" title={meta.email}>
        {meta.email}
      </p>
      <a href="/sign-out" className="text-graphite underline underline-offset-2 hover:text-ink">
        Sign out
      </a>
    </div>
  );
}

export function NavRail() {
  const { meta } = useDisplay();
  return (
    <>
      <nav
        aria-label="Main"
        className="no-print sticky top-0 hidden h-dvh w-52 shrink-0 flex-col justify-between px-4 py-6 md:flex"
      >
        <div>
          <p className="mb-6 px-2 font-semibold text-ink">{meta.store_name}</p>
          <Links />
        </div>
        <div className="flex flex-col gap-4 px-2">
          <DataStamp compact />
          <Account />
        </div>
      </nav>
      <div className="no-print flex items-center justify-between border-rule border-b bg-sheet px-4 py-3 md:hidden">
        <p className="font-semibold">{meta.store_name}</p>
        <Dialog.Root>
          <Dialog.Trigger asChild>
            <button type="button" className="rounded-[var(--radius-control)] border border-rule px-3 py-1.5">
              Menu
            </button>
          </Dialog.Trigger>
          <Dialog.Portal>
            <Dialog.Overlay className="fixed inset-0 z-40 bg-ink/20" />
            <Dialog.Content className="fixed inset-y-0 left-0 z-50 flex w-64 flex-col justify-between bg-sheet p-4 shadow-pop">
              <div>
                <Dialog.Title className="mb-4 px-2 font-semibold">{meta.store_name}</Dialog.Title>
                <Dialog.Close asChild>
                  <div>
                    <Links />
                  </div>
                </Dialog.Close>
              </div>
              <div className="flex flex-col gap-4 px-2">
                <DataStamp compact />
                <Account />
              </div>
            </Dialog.Content>
          </Dialog.Portal>
        </Dialog.Root>
      </div>
    </>
  );
}
