import { useState, type FormEvent } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../auth/AuthProvider";
import { homeFor } from "../auth/roles";
import { FormError, TextField } from "../components/Fields";

export function LoginPage() {
  const { status, role, login } = useAuth();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const [pending, setPending] = useState(false);

  if (status === "authenticated") {
    const from = (location.state as { from?: string } | null)?.from;
    return <Navigate to={from && from !== "/login" ? from : homeFor(role)} replace />;
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setPending(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign in failed.";
      // The API answers a bad email or password with a 401 "No active account found..."
      setError(new Error(msg.startsWith("No active account") ? "Incorrect email or password." : msg));
      setPending(false);
    }
  }

  return (
    <main className="login-screen">
      <div className="login-card">
        <div className="login-brand">
          <div className="brand-mark" aria-hidden="true">IV</div>
          <h1>Inventra</h1>
          <p>Inventory management</p>
        </div>
        <form onSubmit={(e) => void submit(e)} noValidate={false}>
          <TextField label="Email" type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          <TextField label="Password" type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          <FormError error={error} />
          <button type="submit" className="btn btn-primary btn-block" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </main>
  );
}
