import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthProvider";
import { ProtectedRoutes, RequireRole } from "./auth/RequireRole";
import { homeFor } from "./auth/roles";
import { AppShell } from "./layout/AppShell";
import { CatalogPage } from "./pages/CatalogPage";
import { DamagePage } from "./pages/DamagePage";
import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";
import { ProductsPage } from "./pages/ProductsPage";
import { PurchaseOrdersPage } from "./pages/PurchaseOrdersPage";
import { ReportsPage } from "./pages/ReportsPage";
import { ReturnsPage } from "./pages/ReturnsPage";
import { SalesOrdersPage } from "./pages/SalesOrdersPage";
import { TransactionsPage } from "./pages/TransactionsPage";
import { UsersPage } from "./pages/UsersPage";

const guarded = (path: string, element: React.ReactNode) => (
  <Route path={path} element={<RequireRole path={`/${path}`}>{element}</RequireRole>} />
);

function Home() {
  const { role } = useAuth();
  return <Navigate to={homeFor(role)} replace />;
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedRoutes />}>
        <Route element={<AppShell />}>
          <Route index element={<Home />} />
          {guarded("dashboard", <DashboardPage />)}
          {guarded("products", <ProductsPage />)}
          {guarded("catalog", <CatalogPage />)}
          {guarded("purchase-orders", <PurchaseOrdersPage />)}
          {guarded("sales-orders", <SalesOrdersPage />)}
          {guarded("returns", <ReturnsPage />)}
          {guarded("damage", <DamagePage />)}
          {guarded("transactions", <TransactionsPage />)}
          {guarded("reports", <ReportsPage />)}
          {guarded("users", <UsersPage />)}
          <Route path="*" element={<Home />} />
        </Route>
      </Route>
    </Routes>
  );
}
