import type { LineInput } from "../api/resources";
import type { Product } from "../api/types";
import { ProductSelect } from "./ProductSelect";

export interface Line {
  key: number;
  product: Product | null;
  quantity: string;
  unitCost: string;
}

let nextKey = 1;
export const newLine = (): Line => ({ key: nextKey++, product: null, quantity: "1", unitCost: "" });

/** Returns the API payload, or a message describing what is missing. */
export function toItems(lines: Line[], withCost: boolean): { items: LineInput[] } | { error: string } {
  if (lines.length === 0) return { error: "Add at least one line item." };
  const items: LineInput[] = [];
  for (const [i, l] of lines.entries()) {
    const n = i + 1;
    const qty = Number(l.quantity);
    if (!l.product) return { error: `Choose a product for item ${n}.` };
    if (!Number.isInteger(qty) || qty < 1) return { error: `Quantity for item ${n} must be a whole number of at least 1.` };
    if (withCost && (l.unitCost === "" || Number(l.unitCost) < 0)) return { error: `Enter a unit cost for item ${n}.` };
    items.push({ product_id: l.product.id, quantity: qty, ...(withCost ? { unit_cost: l.unitCost } : {}) });
  }
  return { items };
}

interface Props {
  lines: Line[];
  onChange: (lines: Line[]) => void;
  withCost?: boolean;
}

export function LineItemsEditor({ lines, onChange, withCost = false }: Props) {
  const update = (key: number, patch: Partial<Line>) => onChange(lines.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  return (
    <div className="line-items">
      {lines.map((line, i) => {
        const n = i + 1;
        return (
          <fieldset key={line.key} className="line-item">
            <legend>Item {n}</legend>
            <ProductSelect
              label={`Product ${n}`}
              value={line.product}
              onChange={(product) => update(line.key, { product, unitCost: withCost && product && !line.unitCost ? String(product.cost_price) : line.unitCost })}
            />
            <div className="field">
              <label htmlFor={`qty-${line.key}`}>Quantity {n}</label>
              <input id={`qty-${line.key}`} type="number" min={1} step={1} inputMode="numeric" value={line.quantity} onChange={(e) => update(line.key, { quantity: e.target.value })} />
            </div>
            {withCost && (
              <div className="field">
                <label htmlFor={`cost-${line.key}`}>Unit cost {n}</label>
                <input id={`cost-${line.key}`} type="number" min={0} step="0.01" inputMode="decimal" value={line.unitCost} onChange={(e) => update(line.key, { unitCost: e.target.value })} />
              </div>
            )}
            <button type="button" className="btn btn-ghost btn-sm btn-danger" onClick={() => onChange(lines.filter((l) => l.key !== line.key))} aria-label={`Remove item ${n}`}>
              Remove
            </button>
          </fieldset>
        );
      })}
      <button type="button" className="btn btn-sm" onClick={() => onChange([...lines, newLine()])}>
        + Add line item
      </button>
    </div>
  );
}
