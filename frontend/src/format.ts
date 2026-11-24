export function money(v: string | number | null | undefined) {
  const n = Number(v ?? 0);
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function dateTime(v: string | null | undefined) {
  if (!v) return "—";
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export const shortId = (id: string) => id.slice(0, 8);

export function stockStatus(p: { current_stock?: number; low_stock_threshold?: number }): "out" | "low" | "ok" {
  const stock = p.current_stock ?? 0;
  if (stock <= 0) return "out";
  if (stock <= (p.low_stock_threshold ?? 0)) return "low";
  return "ok";
}
