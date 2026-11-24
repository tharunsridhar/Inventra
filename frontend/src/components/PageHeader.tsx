import { useEffect, useRef, type ReactNode } from "react";

/** The page h1. It takes focus on mount so keyboard and screen reader users land on the new page. */
export function PageHeader({ title, actions }: { title: string; actions?: ReactNode }) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    ref.current?.focus();
    document.title = `${title} · Inventra`;
  }, [title]);
  return (
    <div className="page-header">
      <h1 ref={ref} tabIndex={-1}>
        {title}
      </h1>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}
