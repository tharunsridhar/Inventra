// Records the Inventra demo against a locally running stack (docker compose up) that has
// been seeded with `manage.py seed_demo` (demo logins, password demopass123).
//
//   DEMO_URL=http://localhost:3000 node record.mjs
//
// DEMO_URL is the React frontend (docker compose serves it on :3000; `npm run dev` in
// frontend/ serves it on :5173). The frontend proxies /api to the Django API.
//
// Output: inventra-demo.webm and frames/NN.png (key frames used by make_gif.py).
// The UI scenes are live. The last scene is a card quoting the recorded load-test
// results from docs/v2/LOAD_TEST_RESULTS.md; it does not re-run Locust.
//
// Selectors are accessible roles and labels (getByRole, getByLabel), the same ones a
// screen reader sees, so they survive markup and styling changes.
import { chromium } from "playwright";
import { mkdirSync, rmSync, renameSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.DEMO_URL ?? "http://localhost:3000";
const EMAIL = "demo-manager-1@demo.seed";
const PASSWORD = "demopass123";
const W = 1280;
const H = 720;
const stamp = new Date().toISOString().slice(11, 19);
const customer = "Demo Customer " + stamp;
const retryCustomer = "Retry Customer " + stamp;

rmSync(path.join(here, "frames"), { recursive: true, force: true });
rmSync(path.join(here, "video-tmp"), { recursive: true, force: true });
mkdirSync(path.join(here, "frames"), { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
const ctx = await browser.newContext({
  viewport: { width: W, height: H },
  recordVideo: { dir: path.join(here, "video-tmp"), size: { width: W, height: H } },
});
await ctx.addInitScript(() => {
  window.__cap = (text) => {
    let el = document.getElementById("__demo_cap");
    if (!el) {
      el = document.createElement("div");
      el.id = "__demo_cap";
      el.setAttribute("aria-hidden", "true");
      el.style.cssText =
        "position:fixed;left:0;right:0;bottom:0;z-index:99999;padding:14px 24px;" +
        "background:rgba(17,24,39,.92);color:#fff;font:600 22px system-ui,sans-serif;text-align:center;";
      document.documentElement.appendChild(el);
    }
    el.textContent = text;
  };
});
const page = await ctx.newPage();
let frameNo = 0;
const caption = async (text, holdMs = 2600) => {
  await page.evaluate((t) => window.__cap(t), text);
  await page.waitForTimeout(holdMs);
  frameNo += 1;
  await page.screenshot({ path: path.join(here, "frames", String(frameNo).padStart(2, "0") + ".png") });
};
const goTo = async (name) => {
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name, exact: true }).click();
  await page.getByRole("heading", { level: 1, name }).waitFor();
  await page.waitForTimeout(900);
};

// Setup through the API so the scenes cannot fail on stock: pick a product with plenty.
const login = await ctx.request.post(`${BASE}/api/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
if (!login.ok()) throw new Error(`login failed: ${login.status()}; seed the demo data first`);
const { access } = await login.json();
const auth = { Authorization: `Bearer ${access}` };
const prods = await (await ctx.request.get(`${BASE}/api/products/?page_size=100`, { headers: auth })).json();
const product = prods.results.find((p) => p.current_stock >= 20 && !String(p.sku).startsWith("LOADTEST") && p.name.startsWith("Demo"));
if (!product) throw new Error("no product with enough stock found");

// Scene 1: sign in
await page.goto(BASE + "/login");
await page.getByLabel("Email").fill(EMAIL);
await page.getByLabel("Password").fill(PASSWORD);
await caption("Inventra: React + TypeScript frontend, role-based login (Manager)");
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByRole("heading", { level: 1, name: "Dashboard" }).waitFor();
await page.waitForTimeout(1200);
await caption("Dashboard: live stock and order counts, plus a low-stock list");

// Scene 2: products, searched server side
await goTo("Products");
await page.getByLabel("Search", { exact: true }).fill(product.sku);
await page.getByLabel("Search", { exact: true }).press("Enter");
await page.getByRole("cell", { name: product.sku }).waitFor();
await caption(`Products: ${product.name} has ${product.current_stock} units in stock`);

// Scene 3: create a sale with a line item
await goTo("Sales orders");
await page.getByRole("button", { name: "+ New sale" }).click();
const dialog = page.getByRole("dialog", { name: "New sale" });
await dialog.getByLabel("Customer name").fill(customer);
await dialog.getByLabel("Search product 1").fill(product.sku);
await dialog.getByRole("option", { name: new RegExp(product.sku) }).waitFor({ state: "attached" });
await dialog.getByLabel("Product 1", { exact: true }).selectOption({ value: String(product.id) });
await dialog.getByLabel("Quantity 1").fill("3");
await caption("New sale: pick a product by searching, add a quantity");
await dialog.getByRole("button", { name: "Create sale" }).click();
await page.getByText("Sales order created").waitFor();
await page.waitForTimeout(800);

// Scene 4: complete it (stock is deducted atomically, under a row lock)
await page.getByRole("button", { name: `Complete sale for ${customer}` }).click();
await caption("Completing a sale asks first, then deducts stock inside a database transaction");
await page.getByRole("dialog", { name: "Complete sale" }).getByRole("button", { name: "Complete sale", exact: true }).click();
await page.getByText("Sale completed").waitFor();
await page.waitForTimeout(900);
await caption("Sale completed, invoice number issued");

// Scene 5: a retried completion. The order is completed behind the open dialog (a second
// tab, a double click, a retried request), so confirming answers 409.
const created = await ctx.request.post(`${BASE}/api/sales-orders/`, {
  headers: auth,
  data: { customer_name: retryCustomer, items: [{ product_id: product.id, quantity: 1 }] },
});
const retryOrder = await created.json();
await page.reload();
await page.getByRole("button", { name: `Complete sale for ${retryCustomer}` }).click();
await ctx.request.post(`${BASE}/api/sales-orders/${retryOrder.id}/complete/`, { headers: auth, data: {} });
await page.getByRole("dialog", { name: "Complete sale" }).getByRole("button", { name: "Complete sale", exact: true }).click();
await page.getByText("Conflict (409): nothing was changed.").waitFor();
await caption("A retried completion gets a 409. The UI shows the server's message and refreshes the list", 3600);
await page.keyboard.press("Escape");

// Scene 6: the append-only ledger
await goTo("Transactions");
await page.getByLabel("Type").selectOption("sale");
await page.waitForTimeout(900);
await caption("Every stock change is an append-only ledger row; nothing can edit or delete it", 3200);

// Scene 7: recorded load-test results (static card, sourced from the repo docs)
await page.setContent(`<body style="margin:0;background:#0b1020;color:#e5e7eb;font:22px/1.6 system-ui,sans-serif;padding:48px 56px">
<h2 style="margin:0 0 6px">40 concurrent users, 100 units of stock, one product</h2>
<p style="margin:0 0 24px;color:#9ca3af">Recorded Locust results, docs/v2/LOAD_TEST_RESULTS.md (single laptop). Reproduce: loadtest/README.md</p>
<table style="border-collapse:collapse;font:22px ui-monospace,Consolas,monospace">
<tr style="color:#9ca3af"><th style="text-align:left;padding:8px 24px 8px 0">Row locking</th><th style="padding:8px 24px">Sold</th><th style="padding:8px 24px">Stock dropped by</th><th style="padding:8px 24px">Lost updates</th><th style="padding:8px 24px">HTTP errors</th></tr>
<tr><td style="padding:8px 24px 8px 0">OFF</td><td align="center">66</td><td align="center">50</td><td align="center" style="color:#f87171;font-weight:700">16</td><td align="center">0</td></tr>
<tr><td style="padding:8px 24px 8px 0">ON</td><td align="center">78</td><td align="center">78</td><td align="center" style="color:#4ade80;font-weight:700">0</td><td align="center">0</td></tr>
</table>
<p style="margin-top:28px;max-width:1000px">Without locking, concurrent requests do not fail: they silently lose stock updates. <code>select_for_update()</code> makes each sale wait for the previous one to commit.</p></body>`);
await caption("Without row locking 16 stock updates were silently lost. With it: 0.", 6000);

await ctx.close();
await browser.close();

const vids = readdirSync(path.join(here, "video-tmp")).filter((f) => f.endsWith(".webm"));
renameSync(path.join(here, "video-tmp", vids[0]), path.join(here, "inventra-demo.webm"));
rmSync(path.join(here, "video-tmp"), { recursive: true, force: true });
console.log("saved inventra-demo.webm and", frameNo, "frames");
