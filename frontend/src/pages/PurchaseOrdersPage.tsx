import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useProductName, useSupplierName, useSuppliers } from "../api/hooks";
import { api, type LineInput } from "../api/resources";
import type { PurchaseOrder } from "../api/types";
import { Badge } from "../components/Badge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, SelectField } from "../components/Fields";
import { Line, LineItemsEditor, newLine, toItems } from "../components/LineItemsEditor";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { dateTime, money } from "../format";

const PAGE_SIZE = 10;

export function PurchaseOrdersPage() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1) || 1;
  const status = params.get("status") ?? "";
  const [creating, setCreating] = useState(false);
  const [receiving, setReceiving] = useState<PurchaseOrder | null>(null);
  const productName = useProductName();
  const supplierName = useSupplierName();
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const orders = useQuery({
    queryKey: ["purchase-orders", { page, status }],
    queryFn: () => api.purchaseOrders({ page, page_size: PAGE_SIZE, status, ordering: "-created_at" }),
    placeholderData: keepPreviousData,
  });

  const refreshAfterStockChange = () => {
    for (const key of ["purchase-orders", "products", "product-index", "ledger", "dashboard", "notifications"]) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };

  return (
    <>
      <PageHeader title="Purchase orders" actions={<button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>+ New purchase order</button>} />
      <section className="panel" aria-label="Purchase order list">
        <div className="toolbar">
          <SelectField label="Status" value={status} onChange={(e) => setParam("status", e.target.value)}>
            <option value="">All</option>
            <option value="ordered">Ordered</option>
            <option value="received">Received</option>
          </SelectField>
        </div>
        <div className="panel-body">
          <QueryBoundary query={orders} isEmpty={(d) => d.results.length === 0} empty="No purchase orders yet.">
            {(data) => (
              <>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Purchase orders</caption>
                    <thead>
                      <tr>
                        <th scope="col">Supplier</th><th scope="col">Items</th><th scope="col">Total cost</th>
                        <th scope="col">Status</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((po) => {
                        const total = po.items.reduce((sum, i) => sum + i.quantity * Number(i.unit_cost), 0);
                        return (
                          <tr key={po.id}>
                            <td>{supplierName(po.supplier)}</td>
                            <td className="muted">{po.items.map((i) => `${productName(i.product)} × ${i.quantity}`).join(", ")}</td>
                            <td>{money(total)}</td>
                            <td><Badge>{po.status}</Badge></td>
                            <td className="muted">{dateTime(po.created_at)}</td>
                            <td className="row-actions">
                              {po.status === "ordered" && (
                                <button type="button" className="btn btn-primary btn-sm" onClick={() => setReceiving(po)} aria-label={`Receive order from ${supplierName(po.supplier)}`}>
                                  Receive
                                </button>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                <Pagination page={page} pageSize={PAGE_SIZE} count={data.count} onPage={(n) => setParam("page", String(n))} />
              </>
            )}
          </QueryBoundary>
        </div>
      </section>

      {creating && <NewPurchaseDialog onClose={() => setCreating(false)} onCreated={() => { notify("Purchase order created", "success"); void queryClient.invalidateQueries({ queryKey: ["purchase-orders"] }); }} />}
      {receiving && (
        <ConfirmDialog
          title="Receive purchase order"
          message="Receive this purchase order? Stock will be increased. This cannot be undone."
          confirmLabel="Receive"
          onConfirm={() => api.receivePurchaseOrder(receiving.id)}
          onDone={() => {
            notify("Purchase order received", "success");
            refreshAfterStockChange();
          }}
          onConflict={refreshAfterStockChange}
          onClose={() => setReceiving(null)}
        />
      )}
    </>
  );
}

function NewPurchaseDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const suppliers = useSuppliers();
  const [supplier, setSupplier] = useState("");
  const [lines, setLines] = useState<Line[]>(() => [newLine()]);
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (items: LineInput[]) => api.createPurchaseOrder({ supplier_id: supplier, items }),
    onSuccess: () => {
      onCreated();
      onClose();
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!supplier) return setFormError("Choose a supplier.");
    const result = toItems(lines, true);
    if ("error" in result) return setFormError(result.error);
    setFormError(null);
    create.mutate(result.items);
  }

  return (
    <Modal title="New purchase order" onClose={onClose}>
      <form onSubmit={submit}>
        <SelectField label="Supplier" required value={supplier} onChange={(e) => setSupplier(e.target.value)} data-autofocus>
          <option value="">Select a supplier…</option>
          {suppliers.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </SelectField>
        <h3 className="section-title">Line items</h3>
        <LineItemsEditor lines={lines} onChange={setLines} withCost />
        {formError && <div role="alert" className="notice notice-error">{formError}</div>}
        <FormError error={create.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create order"}</button>
        </div>
      </form>
    </Modal>
  );
}
