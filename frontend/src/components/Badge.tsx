import { stockStatus } from "../format";

type Tone = "success" | "warning" | "danger" | "primary";

const TONES: Record<string, Tone> = {
  ordered: "warning", created: "warning", pending: "warning",
  received: "success", completed: "success", approved: "success",
  purchase: "primary", sale: "primary", return: "success", damage: "danger",
};

export function Badge({ children, tone }: { children: string; tone?: Tone }) {
  return <span className={`badge badge-${tone ?? TONES[children] ?? "primary"}`}>{children}</span>;
}

export function StockBadge({ product }: { product: { current_stock?: number; low_stock_threshold?: number } }) {
  const s = stockStatus(product);
  return s === "out" ? <Badge tone="danger">out of stock</Badge> : s === "low" ? <Badge tone="warning">low stock</Badge> : <Badge tone="success">in stock</Badge>;
}
