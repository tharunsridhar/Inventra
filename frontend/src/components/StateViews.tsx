import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";

export function Loading({ label = "Loading…" }: { label?: string }) {
  return (
    <div className="state" role="status">
      <span className="spinner" aria-hidden="true" /> {label}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="state state-empty">{children}</div>;
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <div className="state state-error" role="alert">
      <p>{message}</p>
      {onRetry && (
        <button type="button" className="btn btn-sm" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

/** Renders loading, error and empty states for a query so every page handles all three. */
export function QueryBoundary<T>({
  query,
  isEmpty,
  empty,
  children,
}: {
  query: UseQueryResult<T>;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Loading />;
  if (query.isError) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (isEmpty?.(query.data)) return <EmptyState>{empty ?? "Nothing here yet."}</EmptyState>;
  return <>{children(query.data)}</>;
}
