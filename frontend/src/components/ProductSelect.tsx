import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useId, useState } from "react";
import { api } from "../api/resources";
import type { Product } from "../api/types";

function useDebounced<T>(value: T, ms: number) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

interface Props {
  label: string;
  value: Product | null;
  onChange: (product: Product | null) => void;
  error?: string;
  /** Fixed list of choices (for example the products on one order). Skips the API search. */
  options?: Product[];
}

/**
 * Product picker that searches the API as you type (name or SKU), so it works with a
 * catalog of any size instead of loading the first 100 products into a dropdown.
 */
export function ProductSelect({ label, value, onChange, error, options }: Props) {
  const id = useId();
  const [term, setTerm] = useState("");
  const debounced = useDebounced(term, 250);
  const search = useQuery({
    queryKey: ["product-search", debounced],
    queryFn: () => api.products({ search: debounced, page_size: 20, ordering: "name" }),
    enabled: !options,
    placeholderData: keepPreviousData,
    staleTime: 15_000,
  });

  const list = options ?? search.data?.results ?? [];
  const choices = value && !list.some((p) => p.id === value.id) ? [value, ...list] : list;

  return (
    <div className="field product-select">
      <label htmlFor={id}>{label}</label>
      {!options && (
        <input
          type="search"
          aria-label={`Search ${label.toLowerCase()}`}
          placeholder="Type a name or SKU to narrow the list"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
        />
      )}
      <select
        id={id}
        value={value?.id ?? ""}
        aria-invalid={!!error}
        onChange={(e) => onChange(choices.find((p) => p.id === e.target.value) ?? null)}
      >
        <option value="">Select a product…</option>
        {choices.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name} ({p.sku}) · {p.current_stock ?? 0} in stock
          </option>
        ))}
      </select>
      {!options && search.isError && <span className="field-error">Could not load products. Try typing again.</span>}
      {!options && !search.isError && search.isFetching && <span className="field-hint">Searching…</span>}
      {!options && search.isSuccess && !search.isFetching && list.length === 0 && <span className="field-hint">No products match.</span>}
      {error && <span className="field-error">{error}</span>}
    </div>
  );
}
