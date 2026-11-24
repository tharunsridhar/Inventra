import type { components } from "./schema";

type S = components["schemas"];

// Types generated from the DRF schema (npm run gen:api).
export type Product = S["Product"];
export type ProductInput = S["ProductRequest"];
export type Category = S["Category"];
export type Supplier = S["Supplier"];
export type PurchaseOrder = S["PurchaseOrderRead"];
export type SalesOrder = S["SalesOrderRead"];
export type ReturnRecord = S["ReturnRead"];
export type LedgerEntry = S["InventoryTransactionRead"];
export type AppNotification = S["Notification"];
export type User = S["UserRead"];
export type TokenPair = S["TokenObtainPair"];

export type Role = "admin" | "manager" | "employee";
export type TransactionType = "purchase" | "sale" | "return" | "damage";

export interface Page<T> {
  count: number;
  next?: string | null;
  previous?: string | null;
  results: T[];
}

// The endpoints below are plain APIViews without serializers, so drf-spectacular
// cannot describe them. These types are written by hand from apps/reports/views.py,
// apps/core/views.py and apps/inventory/views.py.
export interface DashboardStats {
  total_products: number;
  total_categories: number;
  total_suppliers: number;
  total_users: number;
  total_purchases: number;
  total_sales: number;
  low_stock_products: number;
  out_of_stock_products: number;
}

export interface TaskStatus {
  task_id: string;
  status: "PENDING" | "STARTED" | "RETRY" | "SUCCESS" | "FAILURE" | string;
  result_url?: string;
  error?: string;
}

export interface InvoiceDispatch {
  task_id: string;
  status_url: string;
}

export interface ReportBase {
  generated_at: string;
  start_date: string | null;
  end_date: string | null;
}
export interface ProductReport extends ReportBase {
  total_count: number;
  items: Array<{ id: string; sku: string; name: string; cost_price: string; selling_price: string; current_stock: number; low_stock_threshold: number; is_active: boolean }>;
}
export interface PurchaseReport extends ReportBase {
  total_orders: number;
  total_cost: string;
  items: Array<{ id: string; supplier_id: string; status: string; created_at: string; total_cost: string }>;
}
export interface SalesReport extends ReportBase {
  total_orders: number;
  total_revenue: string;
  items: Array<{ id: string; status: string; created_at: string; invoice_number: string | null; total_amount: string }>;
}
export interface InventoryReport extends ReportBase {
  summary: { total_purchased: number; total_sold: number; total_returned: number; total_damaged: number };
  transactions: Array<{ id: string; product_id: string; quantity: number; transaction_type: string; reason: string | null; created_at: string }>;
}
export type ReportKind = "products" | "purchases" | "sales" | "inventory";
export interface ReportMap {
  products: ProductReport;
  purchases: PurchaseReport;
  sales: SalesReport;
  inventory: InventoryReport;
}
