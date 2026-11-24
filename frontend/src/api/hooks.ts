import { useQuery } from "@tanstack/react-query";
import { api } from "./resources";
import type { Product, Supplier } from "./types";

const FIVE_MIN = 5 * 60_000;

/**
 * Orders, returns and the ledger only carry product ids. The catalog is loaded once
 * (200 per request, capped at 1000 products) and cached as an id -> product map, so
 * those tables can show names without a request per row. Pickers do not use this:
 * they search the API instead, so they work at any catalog size.
 */
export function useProductIndex() {
  return useQuery({
    queryKey: ["product-index"],
    staleTime: FIVE_MIN,
    queryFn: async () => {
      const map = new Map<string, Product>();
      for (let page = 1; page <= 5; page++) {
        const res = await api.products({ page, page_size: 200 });
        res.results.forEach((p) => map.set(p.id, p));
        if (!res.next) break;
      }
      return map;
    },
  });
}

export function useProductName() {
  const { data } = useProductIndex();
  return (id: string) => data?.get(id)?.name ?? `Product ${id.slice(0, 8)}`;
}

export function useSuppliers() {
  return useQuery({ queryKey: ["suppliers"], queryFn: () => api.suppliers(), staleTime: FIVE_MIN });
}

export function useCategories() {
  return useQuery({ queryKey: ["categories"], queryFn: () => api.categories(), staleTime: FIVE_MIN });
}

export function useSupplierName() {
  const { data } = useSuppliers();
  return (id: string) => (data?.results as Supplier[] | undefined)?.find((s) => s.id === id)?.name ?? "Unknown supplier";
}
