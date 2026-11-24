import { del, get, getPage, patch, post, type Query } from "./client";
import type {
  AppNotification, Category, DashboardStats, InvoiceDispatch, LedgerEntry, Product, ProductInput, PurchaseOrder,
  ReportKind, ReportMap, ReturnRecord, Role, SalesOrder, Supplier, TaskStatus, TokenPair, User,
} from "./types";

export interface LineInput {
  product_id: string;
  quantity: number;
  unit_cost?: string;
}

export const api = {
  // auth
  login: (email: string, password: string) => post<TokenPair>("/auth/login", { email, password }, false),
  logout: (refresh: string) => post("/auth/logout", { refresh }, false),
  me: () => get<User>("/users/me"),

  // dashboard and reports
  dashboard: () => get<DashboardStats>("/dashboard"),
  report: <K extends ReportKind>(kind: K, query: Query) => get<ReportMap[K]>(`/reports/${kind}`, query),

  // catalog
  products: (q: Query) => getPage<Product>("/products", q),
  createProduct: (body: ProductInput) => post<Product>("/products", body),
  updateProduct: (id: string, body: Partial<ProductInput>) => patch<Product>(`/products/${id}`, body),
  deleteProduct: (id: string) => del(`/products/${id}`),
  categories: (q: Query = { page_size: 200 }) => getPage<Category>("/categories", q),
  createCategory: (body: { name: string; description?: string | null }) => post<Category>("/categories", body),
  deleteCategory: (id: string) => del(`/categories/${id}`),
  suppliers: (q: Query = { page_size: 200 }) => getPage<Supplier>("/suppliers", q),
  createSupplier: (body: { name: string; email: string; phone?: string | null; address?: string | null }) => post<Supplier>("/suppliers", body),
  deleteSupplier: (id: string) => del(`/suppliers/${id}`),

  // purchase orders
  purchaseOrders: (q: Query) => getPage<PurchaseOrder>("/purchase-orders", q),
  createPurchaseOrder: (body: { supplier_id: string; items: LineInput[] }) => post<PurchaseOrder>("/purchase-orders", body),
  receivePurchaseOrder: (id: string) => post<PurchaseOrder>(`/purchase-orders/${id}/receive`),

  // sales orders
  salesOrders: (q: Query) => getPage<SalesOrder>("/sales-orders", q),
  createSalesOrder: (body: { customer_name?: string | null; customer_phone?: string | null; items: LineInput[] }) =>
    post<SalesOrder>("/sales-orders", body),
  completeSalesOrder: (id: string) => post<SalesOrder>(`/sales-orders/${id}/complete`),
  requestInvoice: (id: string) => get<InvoiceDispatch>(`/sales-orders/${id}/invoice`),
  task: (id: string) => get<TaskStatus>(`/tasks/${id}`),

  // returns, damage, ledger
  returns: (q: Query) => getPage<ReturnRecord>("/returns", q),
  createReturn: (body: { sales_order: string; product: string; quantity: number; reason: string }) => post<ReturnRecord>("/returns", body),
  approveReturn: (id: string) => patch<ReturnRecord>(`/returns/${id}/approve`),
  writeOffDamage: (body: { product_id: string; quantity: number; reason: string }) => post<LedgerEntry>("/damage", body),
  ledger: (q: Query) => getPage<LedgerEntry>("/inventory-transactions", q),

  // users
  users: (q: Query) => getPage<User>("/users", q),
  createUser: (body: { full_name: string; email: string; password: string; role: Role }) => post<User>("/users", body),
  setRole: (id: string, role: Role) => patch<User>(`/users/${id}/role`, { role }),
  disableUser: (id: string) => del<User>(`/users/${id}`),
  enableUser: (id: string) => patch<User>(`/users/${id}/enable`),
  resetPassword: (id: string, new_password: string) => patch<User>(`/users/${id}/reset-password`, { new_password }),

  // notifications
  notifications: (q: Query) => getPage<AppNotification>("/notifications", q),
  markRead: (id: string) => patch<AppNotification>(`/notifications/${id}/read`),
};
