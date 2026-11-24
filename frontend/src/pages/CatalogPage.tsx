import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ApiError } from "../api/errors";
import { api } from "../api/resources";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, TextAreaField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";
import { useAuth } from "../auth/AuthProvider";
import { isStaff } from "../auth/roles";

type Dialog = { kind: "category" | "supplier" } | { kind: "delete"; what: "category" | "supplier"; id: string; name: string } | null;

export function CatalogPage() {
  const { role } = useAuth();
  const canManage = isStaff(role);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [dialog, setDialog] = useState<Dialog>(null);
  const categories = useQuery({ queryKey: ["categories"], queryFn: () => api.categories() });
  const suppliers = useQuery({ queryKey: ["suppliers"], queryFn: () => api.suppliers() });
  const refresh = (key: "categories" | "suppliers") => {
    void queryClient.invalidateQueries({ queryKey: [key] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  return (
    <>
      <PageHeader title="Categories & suppliers" />

      <section className="panel" aria-labelledby="cat-title">
        <div className="panel-header">
          <h2 id="cat-title">Categories</h2>
          {canManage && <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ kind: "category" })}>+ New category</button>}
        </div>
        <div className="panel-body">
          <QueryBoundary query={categories} isEmpty={(d) => d.results.length === 0} empty="No categories yet.">
            {(data) => (
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Categories</caption>
                  <thead><tr><th scope="col">Name</th><th scope="col">Description</th>{canManage && <th scope="col"><span className="sr-only">Actions</span></th>}</tr></thead>
                  <tbody>
                    {data.results.map((c) => (
                      <tr key={c.id}>
                        <td>{c.name}</td>
                        <td className="muted">{c.description || "—"}</td>
                        {canManage && (
                          <td className="row-actions">
                            <button type="button" className="btn btn-ghost btn-sm btn-danger" aria-label={`Delete category ${c.name}`} onClick={() => setDialog({ kind: "delete", what: "category", id: c.id, name: c.name })}>Delete</button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryBoundary>
        </div>
      </section>

      <section className="panel" aria-labelledby="sup-title">
        <div className="panel-header">
          <h2 id="sup-title">Suppliers</h2>
          {canManage && <button type="button" className="btn btn-primary btn-sm" onClick={() => setDialog({ kind: "supplier" })}>+ New supplier</button>}
        </div>
        <div className="panel-body">
          <QueryBoundary query={suppliers} isEmpty={(d) => d.results.length === 0} empty="No suppliers yet.">
            {(data) => (
              <div className="table-wrap">
                <table>
                  <caption className="sr-only">Suppliers</caption>
                  <thead><tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">Phone</th><th scope="col">Address</th>{canManage && <th scope="col"><span className="sr-only">Actions</span></th>}</tr></thead>
                  <tbody>
                    {data.results.map((s) => (
                      <tr key={s.id}>
                        <td>{s.name}</td>
                        <td>{s.email}</td>
                        <td>{s.phone || "—"}</td>
                        <td className="muted">{s.address || "—"}</td>
                        {canManage && (
                          <td className="row-actions">
                            <button type="button" className="btn btn-ghost btn-sm btn-danger" aria-label={`Delete supplier ${s.name}`} onClick={() => setDialog({ kind: "delete", what: "supplier", id: s.id, name: s.name })}>Delete</button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryBoundary>
        </div>
      </section>

      {dialog?.kind === "category" && <CategoryForm onClose={() => setDialog(null)} onSaved={() => { notify("Category created", "success"); refresh("categories"); }} />}
      {dialog?.kind === "supplier" && <SupplierForm onClose={() => setDialog(null)} onSaved={() => { notify("Supplier created", "success"); refresh("suppliers"); }} />}
      {dialog?.kind === "delete" && (
        <ConfirmDialog
          title={`Delete ${dialog.what}`}
          message={`Delete ${dialog.what} "${dialog.name}"?`}
          confirmLabel="Delete"
          onConfirm={() => (dialog.what === "category" ? api.deleteCategory(dialog.id) : api.deleteSupplier(dialog.id))}
          onDone={() => {
            notify(`${dialog.what === "category" ? "Category" : "Supplier"} deleted`, "success");
            refresh(dialog.what === "category" ? "categories" : "suppliers");
          }}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}

function CategoryForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const save = useMutation({
    mutationFn: () => api.createCategory({ name: name.trim(), description: description.trim() || null }),
    onSuccess: () => { onSaved(); onClose(); },
  });
  const fe = save.error instanceof ApiError ? save.error.fieldErrors : {};
  return (
    <Modal title="New category" onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} error={fe.name?.join(" ")} data-autofocus />
        <TextAreaField label="Description" value={description} onChange={(e) => setDescription(e.target.value)} error={fe.description?.join(" ")} />
        <FormError error={Object.keys(fe).length ? null : save.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Create category"}</button>
        </div>
      </form>
    </Modal>
  );
}

function SupplierForm({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [form, setForm] = useState({ name: "", email: "", phone: "", address: "" });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const save = useMutation({
    mutationFn: () => api.createSupplier({ name: form.name.trim(), email: form.email.trim(), phone: form.phone.trim() || null, address: form.address.trim() || null }),
    onSuccess: () => { onSaved(); onClose(); },
  });
  const fe = save.error instanceof ApiError ? save.error.fieldErrors : {};
  return (
    <Modal title="New supplier" onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); save.mutate(); }}>
        <div className="form-grid">
          <TextField label="Name" required value={form.name} onChange={set("name")} error={fe.name?.join(" ")} data-autofocus />
          <TextField label="Email" type="email" required value={form.email} onChange={set("email")} error={fe.email?.join(" ")} />
          <TextField label="Phone" value={form.phone} onChange={set("phone")} error={fe.phone?.join(" ")} />
          <TextField label="Address" value={form.address} onChange={set("address")} error={fe.address?.join(" ")} />
        </div>
        <FormError error={Object.keys(fe).length ? null : save.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>{save.isPending ? "Saving…" : "Create supplier"}</button>
        </div>
      </form>
    </Modal>
  );
}
