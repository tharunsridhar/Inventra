import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { ApiError } from "../api/errors";
import { api } from "../api/resources";
import type { Role, User } from "../api/types";
import { Badge } from "../components/Badge";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { FormError, SelectField, TextField } from "../components/Fields";
import { Modal } from "../components/Modal";
import { PageHeader } from "../components/PageHeader";
import { Pagination } from "../components/Pagination";
import { QueryBoundary } from "../components/StateViews";
import { useToast } from "../components/Toasts";

const ROLES: Role[] = ["admin", "manager", "employee"];
const PAGE_SIZE = 10;

type Dialog = { kind: "new" } | { kind: "reset"; user: User } | { kind: "disable"; user: User } | null;

export function UsersPage() {
  const [params, setParams] = useSearchParams();
  const page = Number(params.get("page") ?? 1) || 1;
  const [dialog, setDialog] = useState<Dialog>(null);
  const queryClient = useQueryClient();
  const { notify } = useToast();

  const users = useQuery({ queryKey: ["users", { page }], queryFn: () => api.users({ page, page_size: PAGE_SIZE }), placeholderData: keepPreviousData });
  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["users"] });
    void queryClient.invalidateQueries({ queryKey: ["dashboard"] });
  };

  const setRole = useMutation({
    mutationFn: ({ id, role }: { id: string; role: Role }) => api.setRole(id, role),
    onSuccess: () => { notify("Role updated", "success"); refresh(); },
    onError: (e) => { notify(e.message, "error"); refresh(); },
  });
  const enable = useMutation({
    mutationFn: (id: string) => api.enableUser(id),
    onSuccess: () => { notify("User enabled", "success"); refresh(); },
    onError: (e) => notify(e.message, "error"),
  });

  return (
    <>
      <PageHeader title="Users" actions={<button type="button" className="btn btn-primary" onClick={() => setDialog({ kind: "new" })}>+ New user</button>} />
      <section className="panel" aria-label="User list">
        <div className="panel-body">
          <QueryBoundary query={users} isEmpty={(d) => d.results.length === 0} empty="No users.">
            {(data) => (
              <>
                <div className="table-wrap">
                  <table>
                    <caption className="sr-only">Users</caption>
                    <thead><tr><th scope="col">Name</th><th scope="col">Email</th><th scope="col">Role</th><th scope="col">Status</th><th scope="col"><span className="sr-only">Actions</span></th></tr></thead>
                    <tbody>
                      {data.results.map((u) => (
                        <tr key={u.id}>
                          <td>{u.full_name}</td>
                          <td>{u.email}</td>
                          <td>
                            <select aria-label={`Role for ${u.full_name}`} value={u.role} onChange={(e) => setRole.mutate({ id: u.id, role: e.target.value as Role })} disabled={setRole.isPending}>
                              {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                            </select>
                          </td>
                          <td>{u.is_active ? <Badge tone="success">active</Badge> : <Badge tone="danger">disabled</Badge>}</td>
                          <td className="row-actions">
                            {u.is_active ? (
                              <button type="button" className="btn btn-ghost btn-sm btn-danger" onClick={() => setDialog({ kind: "disable", user: u })} aria-label={`Disable ${u.full_name}`}>Disable</button>
                            ) : (
                              <button type="button" className="btn btn-ghost btn-sm" onClick={() => enable.mutate(u.id)} aria-label={`Enable ${u.full_name}`}>Enable</button>
                            )}
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setDialog({ kind: "reset", user: u })} aria-label={`Reset password for ${u.full_name}`}>Reset password</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={page} pageSize={PAGE_SIZE} count={data.count} onPage={(n) => setParams({ page: String(n) }, { replace: true })} />
              </>
            )}
          </QueryBoundary>
        </div>
      </section>

      {dialog?.kind === "new" && <NewUserDialog onClose={() => setDialog(null)} onCreated={() => { notify("User created", "success"); refresh(); }} />}
      {dialog?.kind === "reset" && <ResetPasswordDialog user={dialog.user} onClose={() => setDialog(null)} onDone={() => notify("Password reset", "success")} />}
      {dialog?.kind === "disable" && (
        <ConfirmDialog
          title="Disable user"
          message={`Disable ${dialog.user.full_name}? They will no longer be able to sign in.`}
          confirmLabel="Disable"
          onConfirm={() => api.disableUser(dialog.user.id)}
          onDone={() => { notify("User disabled", "success"); refresh(); }}
          onClose={() => setDialog(null)}
        />
      )}
    </>
  );
}

function NewUserDialog({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "employee" as Role });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const create = useMutation({ mutationFn: () => api.createUser({ ...form, full_name: form.full_name.trim(), email: form.email.trim() }), onSuccess: () => { onCreated(); onClose(); } });
  const fe = create.error instanceof ApiError ? create.error.fieldErrors : {};
  return (
    <Modal title="New user" onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); create.mutate(); }}>
        <div className="form-grid">
          <TextField label="Full name" required value={form.full_name} onChange={set("full_name")} error={fe.full_name?.join(" ")} data-autofocus />
          <TextField label="Email" type="email" required value={form.email} onChange={set("email")} error={fe.email?.join(" ")} />
          <TextField label="Password" type="password" autoComplete="new-password" required minLength={8} hint="At least 8 characters." value={form.password} onChange={set("password")} error={fe.password?.join(" ")} />
          <SelectField label="Role" value={form.role} onChange={set("role")} error={fe.role?.join(" ")}>
            {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
          </SelectField>
        </div>
        <FormError error={Object.keys(fe).length ? null : create.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={create.isPending}>{create.isPending ? "Creating…" : "Create user"}</button>
        </div>
      </form>
    </Modal>
  );
}

function ResetPasswordDialog({ user, onClose, onDone }: { user: User; onClose: () => void; onDone: () => void }) {
  const [password, setPassword] = useState("");
  const reset = useMutation({ mutationFn: () => api.resetPassword(user.id, password), onSuccess: () => { onDone(); onClose(); } });
  const fe = reset.error instanceof ApiError ? reset.error.fieldErrors : {};
  return (
    <Modal title={`Reset password for ${user.full_name}`} onClose={onClose}>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); reset.mutate(); }}>
        <TextField label="New password" type="password" autoComplete="new-password" required minLength={8} hint="At least 8 characters." value={password} onChange={(e) => setPassword(e.target.value)} error={fe.new_password?.join(" ")} data-autofocus />
        <FormError error={Object.keys(fe).length ? null : reset.error} />
        <div className="form-actions">
          <button type="button" className="btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn btn-primary" disabled={reset.isPending}>{reset.isPending ? "Resetting…" : "Reset password"}</button>
        </div>
      </form>
    </Modal>
  );
}
