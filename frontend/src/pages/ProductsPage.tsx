import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../api/errors";
import { useCategories, useSuppliers } from "../api/hooks";
import { api } from "../api/resources";
import type { Product } from "../api/types";
import { StockBadge } from "../components/Badge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, SelectField, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { useAuth } from "../auth/AuthProvider";
import { isStaff } from "../auth/roles";
import { money } from "../format";

const PAGE_SIZE = 10;

export function ProductsPage() {
  const { role } = useAuth();
  const canManage = isStaff(role);
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1) || 1;
  const search = params.get("q") ?? "";
  const stock = params.get("stock") ?? "";
  const category = params.get("category") ?? "";
  const supplier = params.get("supplier") ?? "";

  const [searchText, setSearchText] = useState(search);
  useEffect(() => setSearchText(search), [search]);

  const [editing, setEditing] = useState<Product | "new" | null>(null);
  const [deleting, setDeleting] = useState<Product | null>(null);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const categories = useCategories();
  const suppliers = useSuppliers();

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next, { replace: true });
  };

  const products = useQuery({
    queryKey: ["products", { page, search, stock, category, supplier }],
    queryFn: () => api.products({ page, page_size: PAGE_SIZE, search, stock_status: stock, category_id: category, supplier_id: supplier }),
    placeholderData: keepPreviousData,
  });

  const catName = (id: string) => categories.data?.results.find((c) => c.id === id)?.name ?? "—";
  const supName = (id: string) => suppliers.data?.results.find((s) => s.id === id)?.name ?? "—";
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["products"] });
    void queryClient.invalidateQueries({ queryKey: ["product-index"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  return (
    <>
      <PageHeader
        title="Products"
        actions={
          canManage && (
            <button type="button" className="btn btn-primary" onClick={() => setEditing("new")}>
              + New product
            </button>
          )
        }
      />
      <section className="panel" aria-label="Product list">
        <form
          className="toolbar"
          role="search"
          onSubmit={(e) => {
            e.preventDefault();
            setParam("q", searchText.trim());
          }}
        >
          <div className="field">
            <label htmlFor="prod-search">Search</label>
            <input id="prod-search" type="search" placeholder="Name, SKU, category, supplier" value={searchText} onChange={(e) => setSearchText(e.target.value)} />
          </div>
          <SelectField label="Stock" value={stock} onChange={(e) => setParam("stock", e.target.value)}>
            <option value="">All stock</option>
            <option value="in_stock">In stock</option>
            <option value="low_stock">Low stock</option>
            <option value="out_of_stock">Out of stock</option>
          </SelectField>
          <SelectField label="Category" value={category} onChange={(e) => setParam("category", e.target.value)}>
            <option value="">All categories</option>
            {categories.data?.results.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </SelectField>
          <SelectField label="Supplier" value={supplier} onChange={(e) => setParam("supplier", e.target.value)}>
            <option value="">All suppliers</option>
            {suppliers.data?.results.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </SelectField>
          <button type="submit" className="btn">Search</button>
        </form>

        <div className="panel-body">
          <QueryBoundary query={products} isEmpty={(d) => d.results.length === 0} empty="No products match these filters.">
            {(data) => (
              <>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Products</caption>
                    <thead>
                      <tr>
                        <th scope="col">SKU</th><th scope="col">Name</th><th scope="col">Category</th><th scope="col">Supplier</th>
                        <th scope="col">Cost</th><th scope="col">Price</th><th scope="col">Stock</th><th scope="col">Status</th>
                        {canManage && <th scope="col"><span className="sr-only">Actions</span></th>}
                      </tr>
                    </thead>
                    <tbody>
                      {data.results.map((p) => (
                        <tr key={p.id}>
                          <td className="mono">{p.sku}</td>
                          <td>{p.name}</td>
                          <td>{catName(p.category)}</td>
                          <td>{supName(p.supplier)}</td>
                          <td>{money(p.cost_price)}</td>
                          <td>{money(p.selling_price)}</td>
                          <td>{p.current_stock}</td>
                          <td><StockBadge product={p} /></td>
                          {canManage && (
                            <td className="row-actions">
                              <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(p)} aria-label={`Edit ${p.name}`}>Edit</button>
                              <button type="button" className="btn btn-ghost btn-sm btn-danger" onClick={() => setDeleting(p)} aria-label={`Delete ${p.name}`}>Delete</button>
                            </td>
                          )}
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

      {editing && <ProductForm product={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} notify={notify} />}
      {deleting && (
        <ConfirmDialog
          title="Delete product"
          message={`Delete "${deleting.name}"? It will no longer appear in lists. Its ledger history is kept.`}
          confirmLabel="Delete"
          onConfirm={() => api.deleteProduct(deleting.id)}
          onDone={() => {
            notify("Product deleted", "success");
            refresh();
          }}
          onClose={() => setDeleting(null)}
        />
      )}
    </>
  );
}

function ProductForm({ product, onClose, onSaved, notify }: { product: Product | null; onClose: () => void; onSaved: () => void; notify: (m: string, k?: "success" | "error") => void }) {
  const categories = useCategories();
  const suppliers = useSuppliers();
  const [form, setForm] = useState({
    sku: product?.sku ?? "",
    name: product?.name ?? "",
    description: product?.description ?? "",
    category: product?.category ?? "",
    supplier: product?.supplier ?? "",
    cost_price: product?.cost_price ?? "",
    selling_price: product?.selling_price ?? "",
    current_stock: "0",
    low_stock_threshold: String(product?.low_stock_threshold ?? 5),
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = useMutation({
    mutationFn: () => {
      const body = {
        sku: form.sku.trim(),
        name: form.name.trim(),
        description: form.description.trim() || null,
        category: form.category,
        supplier: form.supplier,
        cost_price: form.cost_price,
        selling_price: form.selling_price,
        low_stock_threshold: Number(form.low_stock_threshold),
        ...(product ? {} : { current_stock: Number(form.current_stock) }),
      };
      return product ? api.updateProduct(product.id, body) : api.createProduct(body);
    },
    onSuccess: () => {
      notify(product ? "Product updated" : "Product created", "success");
      onSaved();
      onClose();
    },
  });
  const fe = save.error instanceof ApiError ? save.error.fieldErrors : {};
  const err = (k: string) => fe[k]?.join(" ");
  // Show the banner only when no field-level message explains the failure.
  const bannerError = save.error && Object.keys(fe).length === 0 ? save.error : null;

  return (
    <Modal title={product ? "Edit product" : "New product"} onClose={onClose}>
      <form
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          save.mutate();
        }}
      >
        <div className="form-grid">
          <TextField label="SKU" required value={form.sku} onChange={set("sku")} error={err("sku")} data-autofocus />
          <TextField label="Name" required value={form.name} onChange={set("name")} error={err("name")} />
          <SelectField label="Category" required value={form.category} onChange={set("category")} error={err("category")}>
            <option value="">Select…</option>
            {categories.data?.results.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </SelectField>
          <SelectField label="Supplier" required value={form.supplier} onChange={set("supplier")} error={err("supplier")}>
            <option value="">Select…</option>
            {suppliers.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </SelectField>
          <TextField label="Cost price" type="number" step="0.01" min="0" required value={form.cost_price} onChange={set("cost_price")} error={err("cost_price")} />
          <TextField label="Selling price" type="number" step="0.01" min="0" required value={form.selling_price} onChange={set("selling_price")} error={err("selling_price")} />
          {!product && <TextField label="Initial stock" type="number" min="0" step="1" value={form.current_stock} onChange={set("current_stock")} error={err("current_stock")} />}
          <TextField label="Low stock threshold" type="number" min="0" step="1" value={form.low_stock_threshold} onChange={set("low_stock_threshold")} error={err("low_stock_threshold")} />
        </div>
        <TextAreaField label="Description" value={form.description} onChange={set("description")} error={err("description")} />
        <FormError error={bannerError} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Saving…" : product ? "Save changes" : "Create product"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
