"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

type Toast = { id: number; text: string; tone: "info" | "error" };
const ToastContext = createContext<(text: string, tone?: Toast["tone"]) => void>(() => undefined);

/** Plain confirmations ("CSV exported") and errors, announced politely to screen readers. */
export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const seq = useRef(0);
  const push = useCallback((text: string, tone: Toast["tone"] = "info") => {
    const id = ++seq.current;
    setToasts((t) => [...t, { id, text, tone }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), tone === "error" ? 8000 : 4000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div
        aria-live="polite"
        className="no-print pointer-events-none fixed right-4 bottom-4 z-50 flex flex-col gap-2"
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.tone === "error" ? "alert" : "status"}
            className="fade-in pointer-events-auto max-w-sm rounded-[var(--radius-control)] border border-rule bg-sheet px-4 py-3 shadow-pop"
          >
            <span className={t.tone === "error" ? "text-signal" : "text-ink"}>{t.text}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  return useContext(ToastContext);
}
