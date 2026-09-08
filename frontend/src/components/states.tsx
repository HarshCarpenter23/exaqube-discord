import type { ReactNode } from "react";
import { ApiError } from "../api/client";

export function Loading({ label }: { label?: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--ink-2)", padding: 16 }}>
      <span className="spinner" /> {label ?? "Loading…"}
    </div>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function ErrorBanner({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  const traceId = error instanceof ApiError ? error.traceId : undefined;
  return (
    <div className="banner error">
      <div>{message}</div>
      {traceId && <div className="mono" style={{ marginTop: 4 }}>trace: {traceId}</div>}
      {onRetry && (
        <button className="btn ghost small" style={{ marginTop: 8 }} onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
