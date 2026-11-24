import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useProductIndex, useProductName } from "../api/hooks";
import { api } from "../api/resources";
import type { Product, ReturnRecord } from "../api/types";
import { Badge } from "../components/Badge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { ProductSelect } from "../components/ProductSelect";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { dateTime, shortId } from "../format";

const PAGE_SIZE = 10;

export function ReturnsPage() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1) || 1;
  const status = params.get("status") ?? "";
  const [filing, setFiling] = useState(false);
  const [approving, setApproving] = useState<ReturnRecord | null>(null);
  const productName = useProductName();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const returns = useQuery({
    queryKey: ["returns", { page, status }],
    queryFn: () => api.returns({ page, page_size: PAGE_SIZE, status }),
    placeholderData: keepPreviousData,
  });
  const refresh = () => {
    for (const key of ["returns", "products", "product-index", "ledger", "dashboard"]) void queryClient.invalidateQueries({ queryKey: [key] });
  };

  return (
    <>
      <PageHeader title="Returns" actions={<button type="button" className="btn btn-primary" onClick={() => setFiling(true)}>+ File return</button>} />
      <section className="panel" aria-label="Return list">
        <div className="toolbar">
          <SelectField label="Status" value={status} onChange={(e) => setParam("status", e.target.value)}>
            <option value="">All</option>
            <option value="pending">Pending</option>
            <option value="approved">Approved</option>
          </SelectField>
        </div>
        <div className="panel-body">
          <QueryBoundary query={returns} isEmpty={(d) => d.results.length === 0} empty="No returns filed.">
            {(data) => (
              <>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Returns</caption>
                    <thead>
                      <tr>
                        <th scope="col">Sales order</th><th scope="col">Product</th><th scope="col">Qty</th><th scope="col">Reason</th>
                        <th scope="col">Status</th><th scope="col">Filed</th><th scope="col"><span className="sr-only">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((r) => (
                        <tr key={r.id}>
                          <td className="mono">{shortId(r.sales_order)}…</td>
                          <td>{productName(r.product)}</td>
                          <td>{r.quantity}</td>
                          <td className="muted">{r.reason}</td>
                          <td><Badge>{r.status}</Badge></td>
                          <td className="muted">{dateTime(r.created_at)}</td>
                          <td className="row-actions">
                            {r.status === "pending" && (
                              <button type="button" className="btn btn-primary btn-sm" onClick={() => setApproving(r)} aria-label={`Approve return of ${productName(r.product)}`}>Approve</button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={page} pageSize={PAGE_SIZE} count={data.count} onPage={(n) => setParam("page", String(n))} />
              </>
            )}
          </QueryBoundary>
        </div>
      </section>

      {filing && <FileReturnDialog onClose={() => setFiling(false)} onFiled={() => { notify("Return filed", "success"); refresh(); }} />}
      {approving && (
        <ConfirmDialog
          title="Approve return"
          message="Approve this return? The returned units go back into stock."
          confirmLabel="Approve"
          onConfirm={() => api.approveReturn(approving.id)}
          onDone={() => { notify("Return approved", "success"); refresh(); }}
          onConflict={refresh}
          onClose={() => setApproving(null)}
        />
      )}
    </>
  );
}

function FileReturnDialog({ onClose, onFiled }: { onClose: () => void; onFiled: () => void }) {
  const [orderId, setOrderId] = useState("");
  const [product, setProduct] = useState<Product | null>(null);
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const index = useProductIndex();

  // Only completed sales can be returned against, so offer exactly those.
  const orders = useQuery({
    queryKey: ["sales-orders", "returnable"],
    queryFn: () => api.salesOrders({ status: "completed", page_size: 50, ordering: "-created_at" }),
  });
  const order = orders.data?.results.find((o) => o.id === orderId);
  const orderProducts = useMemo(
    () => (order ? order.items.map((i) => index.data?.get(i.product)).filter((p): p is Product => !!p) : []),
    [order, index.data],
  );

  const file = useMutation({
    mutationFn: () => api.createReturn({ sales_order: orderId, product: product!.id, quantity: Number(quantity), reason: reason.trim() }),
    onSuccess: () => { onFiled(); onClose(); },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!orderId) return setFormError("Choose the sales order being returned.");
    if (!product) return setFormError("Choose the returned product.");
    if (!Number.isInteger(Number(quantity)) || Number(quantity) < 1) return setFormError("Quantity must be a whole number of at least 1.");
    if (!reason.trim()) return setFormError("Enter a reason for the return.");
    setFormError(null);
    file.mutate();
  }

  return (
    <Modal title="File a return" onClose={onClose}>
      <form onSubmit={submit}>
        <SelectField
          label="Completed sales order"
          required
          value={orderId}
          onChange={(e) => { setOrderId(e.target.value); setProduct(null); }}
          hint={orders.isPending ? "Loading orders…" : orders.isError ? "Could not load sales orders." : undefined}
          data-autofocus
        >
          <option value="">Select an order…</option>
          {orders.data?.results.map((o) => (
            <option key={o.id} value={o.id}>{o.invoice_number} · {o.customer_name || "walk-in"} · {dateTime(o.created_at)}</option>
          ))}
        </SelectField>
        <ProductSelect label="Product" value={product} onChange={setProduct} options={orderProducts} />
        <TextField label="Quantity" type="number" min={1} step={1} value={quantity} onChange={(e) => setQuantity(e.target.value)} />
        <TextAreaField label="Reason" required value={reason} onChange={(e) => setReason(e.target.value)} />
        {formError && <div role="alert" className="notice notice-error">{formError}</div>}
        <FormError error={file.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={file.isPending}>{file.isPending ? "Filing…" : "File return"}</button>
        </div>
      </form>
    </Modal>
  );
}
