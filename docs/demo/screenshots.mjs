// Takes the README screenshots from a running, seeded stack (see record.mjs for setup).
//
//   DEMO_URL=http://localhost:3000 node screenshots.mjs
//
// Output: ../screenshots/*.png
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const out = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "screenshots");
const BASE = process.env.DEMO_URL ?? "http://localhost:3000";
const EMAIL = "demo-manager-1@demo.seed";
const PASSWORD = "demopass123";
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
const page = await ctx.newPage();
const shot = (name) => page.screenshot({ path: path.join(out, name + ".png") });
const goTo = async (name) => {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true }).click();
  await page.getByRole("heading", { level: 1, name }).waitFor();
  await page.waitForLoadState("networkidle");
};

await page.goto(BASE + "/login");
await page.getByLabel("Email").waitFor();
await shot("login");
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Password").fill(PASSWORD);
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByRole("heading", { level: 1, name: "Dashboard" }).waitFor();
await page.waitForLoadState("networkidle");
await shot("dashboard");

await goTo("Products");
await shot("products");

await goTo("Sales orders");
await page.getByRole("button", { name: "+ New sale" }).click();
await page.getByRole("dialog", { name: "New sale" }).getByRole("option").nth(1).waitFor({ state: "attached" });
await shot("new-sale");
await page.keyboard.press("Escape");

// A real 409: open Complete on a created order, complete it through the API behind the
// dialog, then confirm.
const login = await ctx.request.post(`${BASE}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
const auth = { Authorization: `Bearer ${(await login.json()).access}` };
const prods = await (await ctx.request.get(`${BASE}/api/products/?page_size=100`, { headers: auth })).json();
const product = prods.results.find((p) => p.current_stock >= 20 && p.name.startsWith("Demo"));
const order = await (
  await ctx.request.post(`${BASE}/api/sales-orders/`, { headers: auth, data: { customer_name: "Screenshot Customer", items: [{ product_id: product.id, quantity: 1 }] } })
).json();
await page.reload();
await page.getByRole("button", { name: "Complete sale for Screenshot Customer" }).click();
await ctx.request.post(`${BASE}/api/sales-orders/${order.id}/complete/`, { headers: auth, data: {} });
await page.getByRole("dialog", { name: "Complete sale" }).getByRole("button", { name: "Complete sale", exact: true }).click();
await page.getByText("Conflict (409): nothing was changed.").waitFor();
await shot("conflict-409");
await page.keyboard.press("Escape");

await goTo("Transactions");
await shot("transactions");

await page.setViewportSize({ width: 390, height: 844 });
await page.getByRole("button", { name: "Menu" }).click();
await page.waitForTimeout(300);
await shot("phone-menu");

await browser.close();
console.log("saved screenshots to", out);
