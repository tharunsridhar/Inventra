interface Props {
  page: number;
  pageSize: number;
  count: number;
  onPage: (page: number) => void;
}

export function Pagination({ page, pageSize, count, onPage }: Props) {
  const pages = Math.max(1, Math.ceil(count / pageSize));
  return (
    <nav className="pagination" aria-label="Pagination">
      <span aria-live="polite">
        Page {page} of {pages} · {count} total
      </span>
      <button type="button" className="btn btn-sm" onClick={() => onPage(page - 1)} disabled={page <= 1}>
        ← Previous
      </button>
      <button type="button" className="btn btn-sm" onClick={() => onPage(page + 1)} disabled={page >= pages}>
        Next →
      </button>
    </nav>
  );
}
