import type { ReactNode } from "react";
import { Link, Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthProvider";
import { canAccess, homeFor } from "./roles";
import { Loading } from "../components/StateViews";

/** Sends signed-out users to /login and shows a "not allowed" page for pages the role cannot use. */
export function ProtectedRoutes({ children }: { children?: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();
  if (status === "loading") return <Loading label="Restoring your session…" />;
  if (status === "anonymous") return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <>{children ?? <Outlet />}</>;
}

export function RequireRole({ path, children }: { path: string; children: ReactNode }) {
  const { role } = useAuth();
  if (!canAccess(role, path)) {
    return (
      <div className="state" role="alert">
        <h1 tabIndex={-1}>Not available for your role</h1>
        <p>Your account ({role}) cannot open this page.</p>
        <Link to={homeFor(role)}>Go to {homeFor(role).slice(1)}</Link>
      </div>
    );
  }
  return <>{children}</>;
}
