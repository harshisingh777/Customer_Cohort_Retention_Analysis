"use client";

import { useState } from "react";
import { problem } from "@/lib/api/fetcher";
import { useApiMutationFetch } from "@/lib/api/hooks";
import { useDisplay } from "./context";
import { useToast } from "./toast";

type Params = Record<string, string | string[]>;

const button =
  "rounded-[var(--radius-control)] border border-rule bg-sheet px-3 py-1.5 text-sm hover:border-ink disabled:opacity-50";

/** "Export CSV" streams now (anyone); "Export PDF" is a queued job (admins). */
export function ExportButtons({
  csvView,
  pdfView,
  params,
}: {
  csvView?: string;
  pdfView?: string;
  params: Params;
}) {
  const call = useApiMutationFetch();
  const toast = useToast();
  const { isAdmin } = useDisplay();
  const [busy, setBusy] = useState<"csv" | "pdf" | null>(null);

  async function csv() {
    setBusy("csv");
    try {
      const res = await call("POST", "/v1/exports", { format: "csv", view: csvView, params });
      if (!res.ok) throw await problem(res, "the export");
      const blob = await res.blob();
      const name =
        /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? `${csvView}.csv`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = name;
      a.click();
      URL.revokeObjectURL(a.href);
      toast("CSV exported");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't export the CSV. Retry.", "error");
    } finally {
      setBusy(null);
    }
  }

  async function pdfExport() {
    setBusy("pdf");
    try {
      const res = await call("POST", "/v1/exports", { format: "pdf", view: pdfView, params });
      if (!res.ok) throw await problem(res, "the export");
      const { id } = (await res.json()) as { id: string };
      toast("PDF export started. It downloads when ready.");
      for (let i = 0; i < 90; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const s = await call("GET", `/v1/exports/${id}`);
        if (!s.ok) throw await problem(s, "the export");
        const body = (await s.json()) as {
          status: string;
          download_url: string | null;
          error: string | null;
        };
        if (body.status === "succeeded" && body.download_url) {
          window.location.href = body.download_url;
          toast("PDF exported");
          return;
        }
        if (body.status === "failed")
          throw new Error(`Couldn't export the PDF: ${body.error ?? "the export failed"}. Retry.`);
      }
      throw new Error("The PDF is taking longer than 3 minutes. Check the Data page, then retry.");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn't export the PDF. Retry.", "error");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex gap-2">
      {csvView ? (
        <button type="button" className={button} onClick={csv} disabled={busy !== null}>
          {busy === "csv" ? "Exporting" : "Export CSV"}
        </button>
      ) : null}
      {pdfView && isAdmin ? (
        <button type="button" className={button} onClick={pdfExport} disabled={busy !== null}>
          {busy === "pdf" ? "Preparing PDF" : "Export PDF"}
        </button>
      ) : null}
    </div>
  );
}
