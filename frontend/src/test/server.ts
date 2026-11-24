import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const API = "/api";

export const users = {
  admin: { id: "u-admin", email: "demo-admin@demo.seed", full_name: "Demo Admin", role: "admin", is_active: true, created_at: "2026-01-01T00:00:00Z" },
  manager: { id: "u-mgr", email: "demo-manager-1@demo.seed", full_name: "Demo Manager", role: "manager", is_active: true, created_at: "2026-01-01T00:00:00Z" },
  employee: { id: "u-emp", email: "demo-employee-1@demo.seed", full_name: "Demo Employee", role: "employee", is_active: true, created_at: "2026-01-01T00:00:00Z" },
} as const;

export const widget = {
  id: "11111111-1111-4111-8111-111111111111",
  sku: "WID-001",
  name: "Widget",
  description: null,
  cost_price: "40.00",
  selling_price: "100.00",
  current_stock: 25,
  low_stock_threshold: 5,
  category: "c-1",
  supplier: "s-1",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
};

export const page = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

/** Handlers shared by every test: auth plus empty lists, so a page never hits an unmocked URL. */
export const baseHandlers = [
  http.post(`${API}/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email: string; password: string };
    const user = Object.values(users).find((u) => u.email === body.email);
    if (!user || body.password !== "demopass123") {
      return HttpResponse.json({ detail: "No active account found with the given credentials" }, { status: 401 });
    }
    return HttpResponse.json({ access: `access-${user.role}`, refresh: `refresh-${user.role}` });
  }),
  http.get(`${API}/users/me`, ({ request }) => {
    const role = request.headers.get("Authorization")?.replace("Bearer access-", "") as keyof typeof users | undefined;
    const user = role && users[role];
    return user ? HttpResponse.json(user) : HttpResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }),
  http.post(`${API}/auth/refresh`, async ({ request }) => {
    const { refresh } = (await request.json()) as { refresh: string };
    const role = refresh.replace("refresh-", "");
    return HttpResponse.json({ access: `access-${role}`, refresh: `refresh-${role}` });
  }),
  http.post(`${API}/auth/logout`, () => HttpResponse.json({})),
  http.get(`${API}/notifications/`, () => HttpResponse.json(page([]))),
  http.get(`${API}/dashboard`, () =>
    HttpResponse.json({ total_products: 500, total_categories: 8, total_suppliers: 6, total_users: 5, total_purchases: 40, total_sales: 2000, low_stock_products: 3, out_of_stock_products: 1 }),
  ),
  http.get(`${API}/products/`, () => HttpResponse.json(page([widget]))),
  http.get(`${API}/categories/`, () => HttpResponse.json(page([{ id: "c-1", name: "Tools", description: null, is_active: true, created_at: "2026-01-01T00:00:00Z" }]))),
  http.get(`${API}/suppliers/`, () => HttpResponse.json(page([{ id: "s-1", name: "Acme", email: "a@acme.test", phone: null, address: null, is_active: true, created_at: "2026-01-01T00:00:00Z" }]))),
  http.get(`${API}/sales-orders/`, () => HttpResponse.json(page([]))),
];

export const server = setupServer(...baseHandlers);
