import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ApiError } from "../api/errors";
import { useProductName } from "../api/hooks";
import { api } from "../api/resources";
import type { Product } from "../api/types";
import { FormError, TextAreaField, TextField } from "../components/Fields";
import { PageHeader } from "../components/PageHeader";
import { ProductSelect } from "../components/ProductSelect";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { dateTime } from "../format";

export function DamagePage() {
  const [product, setProduct] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const productName = useProductName();

  const recent = useQuery({
    queryKey: ["ledger", { type: "damage", recent: true }],
    queryFn: () => api.ledger({ transaction_type: "damage", page_size: 10, ordering: "-created_at" }),
  });

  const writeOff = useMutation({
    mutationFn: () => api.writeOffDamage({ product_id: product!.id, quantity: Number(quantity), reason: reason.trim() }),
    onSuccess: () => {
      notify("Damage write-off recorded", "success");
      setReason("");
      setProduct(null);
      setQuantity("1");
      for (const key of ["ledger", "products", "product-index", "dashboard", "notifications"]) void queryClient.invalidateQueries({ queryKey: [key] });
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!product) return setFormError("Choose the damaged product.");
    if (!Number.isInteger(Number(quantity)) || Number(quantity) < 1) return setFormError("Quantity must be a whole number of at least 1.");
    if (!reason.trim()) return setFormError("A reason is required for every write-off.");
    setFormError(null);
    writeOff.mutate();
  }

  const conflict = writeOff.error instanceof ApiError && writeOff.error.isConflict;

  return (
    <>
      <PageHeader title="Damage write-off" />
      <section className="panel" aria-labelledby="dmg-form-title">
        <div className="panel-header"><h2 id="dmg-form-title">Log a write-off</h2></div>
        <div className="panel-body">
          <form onSubmit={submit}>
            <ProductSelect label="Product" value={product} onChange={setProduct} />
            <TextField label="Quantity" type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
            <TextAreaField label="Reason" required placeholder="e.g. water damage in the warehouse" value={reason} onChange={(e) => setReason(e.target.value)} />
            {formError && <div role="alert" className="notice notice-error">{formError}</div>}
            {conflict ? (
              <div role="alert" className="notice notice-conflict">
                <strong>Conflict (409): nothing was written off.</strong>
                <p>{writeOff.error?.message}</p>
              </div>
            ) : (
              <FormError error={writeOff.error} />
            )}
            <div className="form-actions">
              <button type="submit" className="btn btn-primary" disabled={writeOff.isPending}>{writeOff.isPending ? "Writing off…" : "Write off stock"}</button>
            </div>
          </form>
        </div>
      </section>

      <section className="panel" aria-labelledby="dmg-recent-title">
        <div className="panel-header"><h2 id="dmg-recent-title">Recent write-offs</h2></div>
        <div className="panel-body">
          <QueryBoundary query={recent} isEmpty={(d) => d.results.length === 0} empty="No damage logged yet.">
            {(data) => (
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Recent damage write-offs</caption>
                  <thead><tr><th scope="col">Product</th><th scope="col">Qty</th><th scope="col">Reason</th><th scope="col">When</th></tr></thead>
                  <tbody>
                    {data.results.map((t) => (
                      <tr key={t.id}>
                        <td>{productName(t.product)}</td>
                        <td>{t.quantity}</td>
                        <td className="muted">{t.reason || "—"}</td>
                        <td className="muted">{dateTime(t.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryBoundary>
        </div>
      </section>
    </>
  );
}
