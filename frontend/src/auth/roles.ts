import type { Role } from "../api/types";

const ALL: Role[] = ["admin", "manager", "employee"];
const STAFF: Role[] = ["admin", "manager"];

export interface NavItem {
  path: string;
  label: string;
  roles: Role[];
}

// Mirrors the DRF permission classes (IsAdmin / IsManagerOrAdmin / IsAnyRole). Hiding a
// page here is convenience only; the API enforces access on every request.
export const NAV_ITEMS: NavItem[] = [
  { path: "/dashboard", label: "Dashboard", roles: STAFF },
  { path: "/products", label: "Products", roles: ALL },
  { path: "/catalog", label: "Categories & suppliers", roles: ALL },
  { path: "/purchase-orders", label: "Purchase orders", roles: STAFF },
  { path: "/sales-orders", label: "Sales orders", roles: ALL },
  { path: "/returns", label: "Returns", roles: STAFF },
  { path: "/damage", label: "Damage write-off", roles: STAFF },
  { path: "/transactions", label: "Transactions", roles: STAFF },
  { path: "/reports", label: "Reports", roles: STAFF },
  { path: "/users", label: "Users", roles: ["admin"] },
];

export const canAccess = (role: Role | undefined, path: string) =>
  !!role && !!NAV_ITEMS.find((i) => i.path === path)?.roles.includes(role);

export const isStaff = (role: Role | undefined) => role === "admin" || role === "manager";

export const homeFor = (role: Role | undefined) => (isStaff(role) ? "/dashboard" : "/products");
