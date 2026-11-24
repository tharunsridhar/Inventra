import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { useProductName } from "../api/hooks";
import { api, type LineInput } from "../api/resources";
import type { SalesOrder } from "../api/types";
import { Badge } from "../components/Badge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, SelectField, TextField } from "../components/Fields";
import { Line, LineItemsEditor, newLine, toItems } from "../components/LineItemsEditor";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { ErrorState, Loading, QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { dateTime, money, shortId } from "../format";

const PAGE_SIZE = 10;

export function SalesOrdersPage() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1) || 1;
  const status = params.get("status") ?? "";
  const [creating, setCreating] = useState(false);
  const [completing, setCompleting] = useState<SalesOrder | null>(null);
  const [invoiceFor, setInvoiceFor] = useState<SalesOrder | null>(null);
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

  const orders = useQuery({
    queryKey: ["sales-orders", { page, status }],
    queryFn: () => api.salesOrders({ page, page_size: PAGE_SIZE, status, ordering: "-created_at" }),
    placeholderData: keepPreviousData,
  });

  // Completing an order changes stock, the ledger, notifications and the dashboard counts.
  const refreshAfterStockChange = () => {
    for (const key of ["sales-orders", "products", "product-index", "ledger", "dashboard", "notifications"]) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };

  return (
    <>
      <PageHeader
        title="Sales orders"
        actions={<button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>+ New sale</button>}
      />
      <section className="panel" aria-label="Sales order list">
        <div className="toolbar">
          <SelectField label="Status" value={status} onChange={(e) => setParam("status", e.target.value)}>
            <option value="">All</option>
            <option value="created">Created</option>
            <option value="completed">Completed</option>
          </SelectField>
        </div>
        <div className="panel-body">
          <QueryBoundary query={orders} isEmpty={(d) => d.results.length === 0} empty="No sales orders yet. Create the first sale.">
            {(data) => (
              <>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Sales orders</caption>
                    <thead>
                      <tr>
                        <th scope="col">Customer</th><th scope="col">Items</th><th scope="col">Total</th><th scope="col">Status</th>
                        <th scope="col">Invoice</th><th scope="col">Created</th><th scope="col"><span className="sr-only">Actions</span></th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((so) => {
                        const total = so.items.reduce((sum, i) => sum + i.quantity * Number(i.unit_price), 0);
                        const label = so.customer_name || `order ${shortId(so.id)}`;
                        return (
                          <tr key={so.id}>
                            <td>{so.customer_name || "—"}</td>
                            <td className="muted">{so.items.map((i) => `${productName(i.product)} × ${i.quantity}`).join(", ")}</td>
                            <td>{money(total)}</td>
                            <td><Badge>{so.status}</Badge></td>
                            <td className="mono">{so.invoice_number || "—"}</td>
                            <td className="muted">{dateTime(so.created_at)}</td>
                            <td className="row-actions">
                              {so.status === "created" ? (
                                <button type="button" className="btn btn-primary btn-sm" onClick={() => setCompleting(so)} aria-label={`Complete sale for ${label}`}>Complete</button>
                              ) : (
                                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setInvoiceFor(so)} aria-label={`View invoice ${so.invoice_number ?? ""}`}>Invoice</button>
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

      {creating && <NewSaleDialog onClose={() => setCreating(false)} onCreated={() => { notify("Sales order created", "success"); void queryClient.invalidateQueries({ queryKey: ["sales-orders"] }); }} />}
      {completing && (
        <ConfirmDialog
          title="Complete sale"
          message="Complete this sale? Stock will be deducted and an invoice number issued. This cannot be undone."
          confirmLabel="Complete sale"
          onConfirm={() => api.completeSalesOrder(completing.id)}
          onDone={() => {
            notify("Sale completed", "success");
            refreshAfterStockChange();
          }}
          // A 409 means the order was already completed (a retry or a second tab) or stock ran out.
          // Refetch so the table shows the real state.
          onConflict={refreshAfterStockChange}
          onClose={() => setCompleting(null)}
        />
      )}
      {invoiceFor && <InvoiceDialog order={invoiceFor} onClose={() => setInvoiceFor(null)} />}
    </>
  );
}

function NewSaleDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [customer, setCustomer] = useState("");
  const [phone, setPhone] = useState("");
  const [lines, setLines] = useState<Line[]>(() => [newLine()]);
  const [formError, setFormError] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: (items: LineInput[]) =>
      api.createSalesOrder({ customer_name: customer.trim() || null, customer_phone: phone.trim() || null, items }),
    onSuccess: () => {
      onCreated();
      onClose();
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    const result = toItems(lines, false);
    if ("error" in result) return setFormError(result.error);
    setFormError(null);
    create.mutate(result.items);
  }

  return (
    <Modal title="New sale" onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <TextField label="Customer name" value={customer} onChange={(e) => setCustomer(e.target.value)} data-autofocus />
          <TextField label="Customer phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        <h3 className="section-title">Line items</h3>
        <LineItemsEditor lines={lines} onChange={setLines} />
        {formError && <div role="alert" className="notice notice-error">{formError}</div>}
        <FormError error={create.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create sale"}</button>
        </div>
      </form>
    </Modal>
  );
}

/**
 * Invoices are PDFs generated by a Celery worker. GET /sales-orders/{id}/invoice/
 * returns 202 plus a task id, then /tasks/{id}/ is polled until the PDF URL is ready.
 */
function InvoiceDialog({ order, onClose }: { order: SalesOrder; onClose: () => void }) {
  const [state, setState] = useState<{ phase: "working" } | { phase: "ready"; url: string } | { phase: "failed"; message: string }>({ phase: "working" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setState({ phase: "working" });
    (async () => {
      try {
        const { task_id } = await api.requestInvoice(order.id);
        for (let i = 0; i < 30; i++) {
          await new Promise((r) => setTimeout(r, 1000));
          if (cancelled) return;
          const t = await api.task(task_id);
          if (t.status === "SUCCESS" && t.result_url) return setState({ phase: "ready", url: t.result_url });
          if (t.status === "FAILURE") return setState({ phase: "failed", message: t.error ?? "Invoice generation failed." });
        }
        setState({ phase: "failed", message: "Timed out waiting for the invoice. Is the Celery worker running?" });
      } catch (e) {
        if (!cancelled) setState({ phase: "failed", message: e instanceof Error ? e.message : "Could not request the invoice." });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [order.id, attempt]);

  return (
    <Modal title={`Invoice ${order.invoice_number ?? ""}`} onClose={onClose}>
      {state.phase === "working" && <Loading label="Generating the invoice PDF…" />}
      {state.phase === "failed" && <ErrorState error={new Error(state.message)} onRetry={() => setAttempt((a) => a + 1)} />}
      {state.phase === "ready" && (
        <p>
          Your invoice is ready.{" "}
          <a className="btn btn-primary" href={state.url} target="_blank" rel="noopener noreferrer">
            Open PDF
          </a>
        </p>
      )}
      <div className="form-actions">
        <button type="button" className="btn" onClick={onClose}>Close</button>
      </div>
    </Modal>
  );
}
