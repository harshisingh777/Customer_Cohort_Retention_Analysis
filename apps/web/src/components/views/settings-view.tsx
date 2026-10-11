"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { problem } from "@/lib/api/fetcher";
import { useApi, useApiMutationFetch } from "@/lib/api/hooks";
import type { Schemas } from "@/lib/api/types";
import { PageHeader } from "../app-shell";
import { useDisplay } from "../context";
import { Sheet, SheetHeader } from "../sheet";
import { QueryView, SheetBoundary } from "../states";
import { Term } from "../term";
import { useToast } from "../toast";

const input = "w-full rounded-[var(--radius-control)] border border-rule bg-sheet px-2 py-1.5";
const button = "rounded-[var(--radius-control)] bg-ink px-3 py-1.5 text-sheet disabled:opacity-60";

function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: React.ReactNode;
  hint?: string;
  children: React.ReactNode;
  htmlFor: string;
}) {
  return (
    <div className="grid grid-cols-1 gap-1 border-rule border-b py-3 last:border-0 sm:grid-cols-[220px_1fr] sm:gap-4">
      <label htmlFor={htmlFor} className="pt-1.5">
        {label}
        {hint ? <span className="block text-graphite text-xs">{hint}</span> : null}
      </label>
      <div>{children}</div>
    </div>
  );
}

function SettingsForm({ s }: { s: Schemas["SettingsOut"] }) {
  const call = useApiMutationFetch();
  const toast = useToast();
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  async function save(form: FormData) {
    setBusy(true);
    const num = (k: string) => {
      const v = String(form.get(k) ?? "").trim();
      return v === "" ? null : Number(v);
    };
    const lapse = num("lapse_threshold_days");
    const margin = num("gross_margin");
    const body = {
      store_name: String(form.get("store_name")),
      reporting_tz: String(form.get("reporting_tz")),
      reporting_currency: String(form.get("reporting_currency")).toUpperCase(),
      locale: String(form.get("locale")),
      refresh_time_local: String(form.get("refresh_time_local")),
      qualifying_statuses: String(form.get("qualifying_statuses"))
        .split(",")
        .map((x) => x.trim().toLowerCase())
        .filter(Boolean),
      ...(lapse != null ? { lapse_threshold_days: lapse } : {}),
      ...(margin != null ? { gross_margin: margin / 100 } : {}),
      clear: [
        ...(lapse == null ? ["lapse_threshold_days"] : []),
        ...(margin == null ? ["gross_margin"] : []),
      ],
    };
    try {
      const res = await call("PUT", "/v1/settings", body);
      if (!res.ok) throw await problem(res, "settings");
      const out = (await res.json()) as { rebuild_job_id: number | null };
      toast(
        out.rebuild_job_id
          ? "Settings saved. The numbers are rebuilding; the Data page shows progress."
          : "Settings saved.",
      );
      await qc.invalidateQueries();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't save settings.", "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <form action={save}>
      <Field label="Store name" htmlFor="store_name">
        <input id="store_name" name="store_name" defaultValue={s.store_name} className={input} required />
      </Field>
      <Field
        label="Reporting timezone"
        hint="Cohorts and months are counted in this timezone."
        htmlFor="reporting_tz"
      >
        <input
          id="reporting_tz"
          name="reporting_tz"
          defaultValue={s.reporting_tz}
          className={input}
          required
        />
      </Field>
      <Field
        label="Reporting currency"
        hint="Other currencies convert at the order date's reference rate."
        htmlFor="reporting_currency"
      >
        <input
          id="reporting_currency"
          name="reporting_currency"
          defaultValue={s.reporting_currency}
          maxLength={3}
          className={input}
          required
        />
      </Field>
      <Field label="Number format" hint="Locale, e.g. en-GB" htmlFor="locale">
        <input id="locale" name="locale" defaultValue={s.locale} className={input} required />
      </Field>
      <Field
        label={<Term id="qualifying_order">Qualifying order statuses</Term>}
        hint="Comma separated. Orders in other statuses don't count."
        htmlFor="qualifying_statuses"
      >
        <input
          id="qualifying_statuses"
          name="qualifying_statuses"
          defaultValue={s.qualifying_statuses.join(", ")}
          className={input}
        />
      </Field>
      <Field
        label={<Term id="lapse_threshold">Lapse threshold override</Term>}
        hint="Days. Leave empty to derive it from this store's own purchase gaps."
        htmlFor="lapse_threshold_days"
      >
        <input
          id="lapse_threshold_days"
          name="lapse_threshold_days"
          type="number"
          min={1}
          max={3650}
          defaultValue={s.lapse_threshold_days ?? ""}
          className={input}
        />
      </Field>
      <Field
        label={<Term id="payback_month">Gross margin</Term>}
        hint="Percent. An assumption used only for payback. Leave empty to hide payback."
        htmlFor="gross_margin"
      >
        <input
          id="gross_margin"
          name="gross_margin"
          type="number"
          min={1}
          max={100}
          step="0.1"
          defaultValue={s.gross_margin != null ? Math.round(s.gross_margin * 1000) / 10 : ""}
          className={input}
        />
      </Field>
      <Field label="Daily refresh time" hint="Local time, HH:MM." htmlFor="refresh_time_local">
        <input
          id="refresh_time_local"
          name="refresh_time_local"
          defaultValue={s.refresh_time_local}
          pattern="\d{2}:\d{2}"
          className={input}
        />
      </Field>
      <div className="mt-4 flex items-center gap-3">
        <button type="submit" className={button} disabled={busy}>
          {busy ? "Saving" : "Save settings"}
        </button>
        <span className="text-graphite text-sm">Changing a definition rebuilds every number.</span>
      </div>
    </form>
  );
}

function Users() {
  const users = useApi("/v1/users", {}, "users");
  const call = useApiMutationFetch();
  const toast = useToast();
  const { fmt, meta } = useDisplay();
  async function act(method: string, path: string, body: unknown, done: string) {
    const res = await call(method, path, body);
    if (!res.ok) {
      toast((await problem(res, "the user")).detail, "error");
      return;
    }
    toast(done);
    await users.refetch();
  }
  return (
    <>
      <form
        action={(f) =>
          act(
            "POST",
            "/v1/users",
            { email: String(f.get("email")), role: String(f.get("role")) },
            "Invitation saved. They can sign in with that email.",
          )
        }
        className="mb-4 flex flex-wrap items-end gap-3"
      >
        <label className="flex flex-col gap-1">
          <span className="text-graphite text-sm">Email</span>
          <input name="email" type="email" required className={input} />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-graphite text-sm">Role</span>
          <select name="role" className={input} defaultValue="viewer">
            <option value="viewer">Viewer</option>
            <option value="admin">Admin</option>
          </select>
        </label>
        <button type="submit" className={button}>
          Invite
        </button>
      </form>
      <QueryView query={users} rows={4}>
        {(list) => (
          <table className="w-full text-sm">
            <caption className="sr-only">People with access</caption>
            <thead>
              <tr className="border-rule border-b text-graphite">
                <th scope="col" className="py-2 text-left font-normal">
                  Email
                </th>
                <th scope="col" className="py-2 text-left font-normal">
                  Role
                </th>
                <th scope="col" className="py-2 text-left font-normal">
                  Last seen
                </th>
                <th scope="col" className="py-2 text-right font-normal">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.email} className="border-rule border-b last:border-0">
                  <td className="py-2">
                    {u.email}
                    {u.disabled ? <span className="text-graphite"> (disabled)</span> : null}
                  </td>
                  <td className="py-2">
                    <select
                      aria-label={`Role for ${u.email}`}
                      value={u.role}
                      disabled={u.email === meta.email}
                      onChange={(e) =>
                        act(
                          "PATCH",
                          `/v1/users/${encodeURIComponent(u.email)}`,
                          { role: e.target.value },
                          "Role changed.",
                        )
                      }
                      className="rounded-[var(--radius-control)] border border-rule bg-sheet px-1 py-0.5"
                    >
                      <option value="viewer">Viewer</option>
                      <option value="admin">Admin</option>
                    </select>
                  </td>
                  <td className="py-2">{u.last_seen_at ? fmt.dateTime(u.last_seen_at) : "Never"}</td>
                  <td className="py-2 text-right">
                    {u.email !== meta.email ? (
                      <button
                        type="button"
                        onClick={() =>
                          act(
                            "DELETE",
                            `/v1/users/${encodeURIComponent(u.email)}`,
                            undefined,
                            "Access removed.",
                          )
                        }
                        className="text-graphite underline underline-offset-4"
                      >
                        Remove
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </QueryView>
    </>
  );
}

export function SettingsView() {
  const settings = useApi("/v1/settings", {}, "settings");
  return (
    <>
      <PageHeader
        title="Settings"
        lede="Definitions that shape every number, and who has access. Changes are audited."
      />
      <div className="flex flex-col gap-6">
        <Sheet labelledBy="settings-title">
          <SheetHeader title="Store and definitions" id="settings-title" />
          <SheetBoundary>
            <QueryView query={settings} rows={8}>
              {(s) => <SettingsForm s={s} />}
            </QueryView>
          </SheetBoundary>
        </Sheet>
        <Sheet labelledBy="users-title">
          <SheetHeader
            title="People with access"
            id="users-title"
            description="Invite-only. Viewers see masked emails; admins see full addresses and can change settings."
          />
          <SheetBoundary>
            <Users />
          </SheetBoundary>
        </Sheet>
      </div>
    </>
  );
}
