// Records the full Inventra demo against a locally running stack (docker compose up) that
// has been seeded with `manage.py seed_demo` (demo logins, password demopass123).
//
//   DEMO_URL=http://localhost:3000 API_URL=http://localhost:8000 node record.mjs
//
// DEMO_URL is the React frontend (docker compose serves it on :3000; `npm run dev` in
// frontend/ serves it on :5173). API_URL is Django, used only for the Swagger scene.
//
// Output: inventra-demo.webm and frames/NN.png (key frames used by make_gif.py).
// make_gif.py builds the GIF and make_mp4.py builds the MP4 from the WebM.
// The UI scenes are live. The test and load-test scenes are cards quoting recorded
// results; they do not re-run the suites.
//
// Selectors are accessible roles and labels (getByRole, getByLabel), the same ones a
// screen reader sees, so they survive markup and styling changes.
import { chromium } from "playwright";
import { mkdirSync, rmSync, renameSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.DEMO_URL ?? "http://localhost:3000";
const API_URL = process.env.API_URL ?? "http://localhost:8000";
const PASSWORD = "demopass123";
const ACCOUNTS = {
  manager: "demo-manager-1@demo.seed",
  employee: "demo-employee-1@demo.seed",
  admin: "demo-admin@demo.seed",
};
const W = 1280;
const H = 720;
const stamp = new Date().toISOString().slice(11, 19);
const customer = "Demo Customer " + stamp;
const retryCustomer = "Retry Customer " + stamp;
const returnReason = "Demo return " + stamp;
const today = new Date().toISOString().slice(0, 10);
const monthStart = today.slice(0, 8) + "01";

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
const caption = async (text, holdMs = 2400) => {
  await page.evaluate((t) => window.__cap(t), text);
  await page.waitForTimeout(holdMs);
  frameNo += 1;
  await page.screenshot({ path: path.join(here, "frames", String(frameNo).padStart(2, "0") + ".png") });
};
const nav = page.getByRole("navigation", { name: "Main" });
const goTo = async (name) => {
  await nav.getByRole("link", { name, exact: true }).click();
  await page.getByRole("heading", { level: 1, name }).waitFor();
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(500);
};
const signIn = async (who, { slow = false } = {}) => {
  await page.getByLabel("Email").fill(ACCOUNTS[who]);
  await page.getByLabel("Password").fill(PASSWORD);
  if (slow) await caption(`Signing in as ${who}`, 1400);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByRole("button", { name: "Log out" }).waitFor();
  await page.waitForLoadState("networkidle");
};
const signOut = async () => {
  await page.getByRole("button", { name: "Log out" }).click();
  await page.getByRole("button", { name: "Sign in" }).waitFor();
};
const navLinks = async () => (await nav.getByRole("link").allTextContents()).join(", ");
const confirmBtn = (title, label) => page.getByRole("dialog", { name: title }).getByRole("button", { name: label, exact: true });

// Setup through the API so no scene can fail on stock: pick a product with plenty.
const login = await ctx.request.post(`${BASE}/api/auth/login`, { data: { email: ACCOUNTS.manager, password: PASSWORD } });
if (!login.ok()) throw new Error(`login failed: ${login.status()}; seed the demo data first`);
const auth = { Authorization: `Bearer ${(await login.json()).access}` };
const prods = await (await ctx.request.get(`${BASE}/api/products/?page_size=100`, { headers: auth })).json();
const product = prods.results.find((p) => p.current_stock >= 50 && !String(p.sku).startsWith("LOADTEST") && p.name.startsWith("Demo"));
if (!product) throw new Error("no product with enough stock found");
const searchSku = async (label = "Search") => {
  const box = page.getByLabel(label, { exact: true });
  await box.fill(product.sku);
  await box.press("Enter");
  await page.getByRole("cell", { name: product.sku }).waitFor();
};

/* ------------------------------ 1. opening ------------------------------ */
await page.goto(BASE + "/login");
await page.getByLabel("Email").waitFor();
await caption("Inventra: inventory management, React + TypeScript frontend over a Django REST API", 2800);
await page.getByLabel("Email").fill(ACCOUNTS.manager);
await page.getByLabel("Password").fill("not-the-password");
await page.getByRole("button", { name: "Sign in" }).click();
await page.getByText("Incorrect email or password.").waitFor();
await caption("A wrong password gets a clear error and no token is stored");
// /auth/* is throttled to 10 requests a minute, so sign-ins are kept few and spread out.
await signIn("employee");
await caption("Employee login: only Products, Categories & suppliers and Sales orders", 3000);
await page.goto(BASE + "/returns");
await page.getByText("Not available for your role").waitFor();
await caption("A staff-only URL typed by an employee shows 'not available' (the API refuses it too)", 3200);
await signOut();
await page.waitForTimeout(1500);
await signIn("manager");
// Sign-in returns to the page the employee was on (/returns); go to the dashboard.
await goTo("Dashboard");
await caption("Manager login: dashboard with live counts and a low-stock list");
await caption(`Manager navigation: ${await navLinks()}`, 3200);

/* ------------------------------ 3. products ------------------------------ */
await goTo("Products");
await searchSku();
await caption(`Products: search by SKU. ${product.name} has ${product.current_stock} units in stock`);
await page.getByLabel("Search", { exact: true }).fill("");
await page.getByLabel("Search", { exact: true }).press("Enter");
await page.getByLabel("Category").selectOption({ index: 1 });
await page.waitForLoadState("networkidle");
await page.getByLabel("Supplier").selectOption({ index: 1 });
await page.waitForLoadState("networkidle");
await page.waitForTimeout(600);
await caption("Filter by category and supplier; filters live in the URL so a view is linkable");
await page.getByLabel("Category").selectOption("");
await page.getByLabel("Supplier").selectOption("");
await page.waitForLoadState("networkidle");
const next = page.getByRole("button", { name: /Next/ });
if (await next.isEnabled()) {
  await next.click();
  await page.waitForLoadState("networkidle");
  await caption("Server-side pagination across 500 products");
}

/* --------------------------- 4. sales, the core flow --------------------------- */
await goTo("Sales orders");
await page.getByRole("button", { name: "+ New sale" }).click();
const saleDialog = page.getByRole("dialog", { name: "New sale" });
await saleDialog.getByLabel("Customer name").fill(customer);
await saleDialog.getByLabel("Search product 1").fill(product.sku);
await saleDialog.getByRole("option", { name: new RegExp(product.sku) }).waitFor({ state: "attached" });
await saleDialog.getByLabel("Product 1", { exact: true }).selectOption({ value: String(product.id) });
await saleDialog.getByLabel("Quantity 1").fill("3");
await caption("New sale: the product picker searches the API as you type, so it works at any catalog size");
await saleDialog.getByRole("button", { name: "Create sale" }).click();
await page.getByText("Sales order created").waitFor();
await page.waitForTimeout(800);

await page.getByRole("button", { name: `Complete sale for ${customer}` }).click();
await caption("Completing a sale asks first, then deducts stock inside a database transaction");
await confirmBtn("Complete sale", "Complete sale").click();
await page.getByText("Sale completed").waitFor();
await page.waitForTimeout(900);
await caption("Sale completed and an invoice number issued");

await page.getByRole("row", { name: new RegExp(customer) }).getByRole("button", { name: /View invoice/ }).click();
await caption("Invoice: a Celery worker generates the PDF; the UI polls the task", 1800);
await page.getByRole("link", { name: "Open PDF" }).waitFor({ timeout: 40000 });
await caption("Invoice PDF ready");
await page.keyboard.press("Escape");

// A retried completion: the order is completed behind the open dialog (a second tab, a
// double click, a retried request), so confirming answers 409.
const created = await ctx.request.post(`${BASE}/api/sales-orders/`, {
  headers: auth,
  data: { customer_name: retryCustomer, items: [{ product_id: product.id, quantity: 1 }] },
});
if (!created.ok()) throw new Error(`could not create the retry order: ${created.status()} ${await created.text()}`);
const retryOrder = await created.json();
await page.reload();
await page.getByRole("button", { name: `Complete sale for ${retryCustomer}` }).click();
await ctx.request.post(`${BASE}/api/sales-orders/${retryOrder.id}/complete/`, { headers: auth, data: {} });
await confirmBtn("Complete sale", "Complete sale").click();
await page.getByText("Conflict (409): nothing was changed.").waitFor();
await caption("A retried completion gets a 409. The UI shows the server's message and refreshes the list", 3600);
await page.keyboard.press("Escape");

/* ----------------------- 5. purchase orders, stock in ----------------------- */
await goTo("Purchase orders");
await page.getByRole("button", { name: "+ New purchase order" }).click();
const poDialog = page.getByRole("dialog", { name: "New purchase order" });
await poDialog.getByLabel("Supplier").selectOption({ index: 1 });
await poDialog.getByLabel("Search product 1").fill(product.sku);
await poDialog.getByRole("option", { name: new RegExp(product.sku) }).waitFor({ state: "attached" });
await poDialog.getByLabel("Product 1", { exact: true }).selectOption({ value: String(product.id) });
await poDialog.getByLabel("Quantity 1").fill("20");
await caption("New purchase order: supplier, line items; unit cost is prefilled from the product");
await poDialog.getByRole("button", { name: "Create order" }).click();
await page.getByText("Purchase order created").waitFor();
await page.waitForTimeout(800);
await page.getByRole("button", { name: /^Receive order from/ }).first().click();
await caption("Receiving a purchase order adds the stock, once, under a row lock");
await confirmBtn("Receive purchase order", "Receive").click();
await page.getByText("Purchase order received").waitFor();
await page.waitForTimeout(900);
await goTo("Products");
await searchSku();
await caption("Stock went up by 20 after the purchase order was received");

/* --------------------------- 6. returns and damage --------------------------- */
await goTo("Returns");
await page.getByRole("button", { name: "+ File return" }).click();
const retDialog = page.getByRole("dialog", { name: "File a return" });
const saleOrders = await (await ctx.request.get(`${BASE}/api/sales-orders/?status=completed&page_size=20`, { headers: auth })).json();
const soldOrder = saleOrders.results.find((o) => o.customer_name === customer);
await retDialog.getByLabel("Completed sales order").selectOption(soldOrder.id);
await retDialog.getByRole("option", { name: new RegExp(product.name) }).waitFor({ state: "attached" });
await retDialog.getByLabel("Product", { exact: true }).selectOption({ value: String(product.id) });
await retDialog.getByLabel("Reason").fill(returnReason);
await caption("File a return: only completed sales are offered, and only the products on that order");
await retDialog.getByRole("button", { name: "File return" }).click();
await page.getByText("Return filed").waitFor();
await page.waitForTimeout(800);
await page.getByRole("row", { name: new RegExp(returnReason) }).getByRole("button", { name: /Approve return/ }).click();
await confirmBtn("Approve return", "Approve").click();
await page.getByText("Return approved").waitFor();
await caption("Approving a return puts the units back into stock");

await goTo("Damage write-off");
await page.getByLabel("Search product").fill(product.sku);
await page.getByRole("option", { name: new RegExp(product.sku) }).waitFor({ state: "attached" });
await page.getByLabel("Product", { exact: true }).selectOption({ value: String(product.id) });
await page.getByLabel("Reason").fill("Water damage in the warehouse");
await page.getByRole("button", { name: "Write off stock" }).click();
await page.getByText("Damage write-off recorded").waitFor();
await caption("Damage write-off: a reason is required and the entry lands in the ledger");
await page.getByLabel("Search product").fill(product.sku);
await page.getByRole("option", { name: new RegExp(product.sku) }).waitFor({ state: "attached" });
await page.getByLabel("Product", { exact: true }).selectOption({ value: String(product.id) });
await page.getByLabel("Quantity").fill("999999");
await page.getByLabel("Reason").fill("Too many to be true");
await page.getByRole("button", { name: "Write off stock" }).click();
await page.getByText("Conflict (409): nothing was written off.").waitFor();
await caption("Writing off more than is in stock is refused with a 409 and nothing changes", 3000);

/* ---------------------- 7. ledger and notifications ---------------------- */
await goTo("Transactions");
await caption("Every action above is a ledger row: purchase, sale, return, damage");
await page.getByLabel("Type").selectOption("sale");
await page.waitForLoadState("networkidle");
await page.waitForTimeout(600);
await caption("Filter by type. The ledger is append-only: no edit or delete route exists", 3200);
await page.getByRole("button", { name: /^Notifications/ }).click();
await page.getByRole("dialog", { name: "Notifications" }).waitFor();
await page.waitForTimeout(700);
await caption("Notifications drawer with an unread count");
const markRead = page.getByRole("dialog", { name: "Notifications" }).getByRole("button", { name: "Mark as read" }).first();
if (await markRead.count()) {
  await markRead.click();
  await page.waitForTimeout(900);
  await caption("Mark as read updates the badge");
}
await page.keyboard.press("Escape");

/* -------------------------------- 8. reports -------------------------------- */
await goTo("Reports");
await page.getByLabel("Report", { exact: true }).selectOption("sales");
await page.getByLabel("From").fill(monthStart);
await page.getByLabel("To").fill(today);
await page.getByRole("button", { name: "Run report" }).click();
await page.getByText("Revenue").waitFor();
await page.waitForTimeout(700);
await caption("Reports render as tables with a date range, not raw JSON");

/* ------------------------ 9. accessibility, keyboard ------------------------ */
await goTo("Sales orders");
await page.reload();
await page.getByRole("button", { name: "Log out" }).waitFor();
await page.keyboard.press("Tab");
await caption("Keyboard only: the first Tab reveals a skip link", 2200);
await page.getByRole("button", { name: "+ New sale" }).focus();
await page.keyboard.press("Enter");
await page.getByRole("dialog", { name: "New sale" }).waitFor();
await page.keyboard.press("Tab");
await page.keyboard.press("Tab");
await caption("Dialogs take focus, trap Tab inside, and Escape closes them", 2600);
await page.keyboard.press("Escape");
await page.waitForTimeout(400);
await caption("Focus returns to the button that opened the dialog", 2200);

/* ----------------------------- 10. phone width ----------------------------- */
await page.setContent(
  `<body style="margin:0;background:#0b1020;display:flex;justify-content:center;align-items:center;height:100vh;gap:40px;color:#e5e7eb;font:22px system-ui,sans-serif">
   <div style="width:340px">Phone width (390px). The sidebar collapses behind a Menu button and tables scroll sideways.</div>
   <iframe id="phone" src="${BASE}/sales-orders" title="Phone view" style="width:390px;height:640px;border:10px solid #1f2937;border-radius:28px;background:#fff"></iframe></body>`,
);
const phone = page.frameLocator("#phone");
await phone.getByRole("button", { name: "Menu" }).waitFor();
await phone.getByRole("button", { name: "Menu" }).click();
await page.waitForTimeout(700);
await caption("Usable at phone width", 2800);

/* ------------------------------- 11. users (admin) ------------------------------- */
await page.goto(BASE + "/sales-orders");
await page.getByRole("button", { name: "Log out" }).waitFor();
await signOut();
await page.waitForTimeout(1500);
await signIn("admin");
await caption(`Admin sees every page, including Users: ${(await navLinks()).split(", ").slice(-3).join(", ")}`, 2800);
await goTo("Users");
await page.getByRole("button", { name: "+ New user" }).click();
const userDialog = page.getByRole("dialog", { name: "New user" });
const newName = "Demo Hire " + stamp;
await userDialog.getByLabel("Full name").fill(newName);
await userDialog.getByLabel("Email").fill(`hire-${stamp.replace(/:/g, "")}@demo.seed`);
await userDialog.getByLabel("Password").fill("a-long-demo-password");
await caption("Admin only: create a user and choose a role");
await userDialog.getByRole("button", { name: "Create user" }).click();
await page.getByText("User created").waitFor();
await page.waitForTimeout(800);
await page.getByLabel(`Role for ${newName}`).selectOption("manager");
await page.getByText("Role updated").waitFor();
await caption("Change a role in place; the API enforces who may do this", 2800);

/* ------------------------------- 12. engineering proof ------------------------------- */
await page.goto(`${API_URL}/api/docs/`);
await page.getByText("Inventra API").first().waitFor();
await page.waitForTimeout(1200);
await caption("Typed API: Swagger from drf-spectacular; the frontend types are generated from this schema", 3200);

await page.setContent(`<body style="margin:0;background:#0b1020;color:#e5e7eb;font:22px/1.6 system-ui,sans-serif;padding:48px 56px">
<h2 style="margin:0 0 6px">Tested at both ends</h2>
<p style="margin:0 0 24px;color:#9ca3af">Run in CI on every push (.github/workflows/ci.yml)</p>
<table style="border-collapse:collapse;font:22px ui-monospace,Consolas,monospace">
<tr><td style="padding:8px 32px 8px 0">Backend: pytest + ruff</td><td style="color:#4ade80;font-weight:700">31 passed</td></tr>
<tr><td style="padding:8px 32px 8px 0">Frontend: Vitest + Testing Library</td><td style="color:#4ade80;font-weight:700">19 passed</td></tr>
<tr><td style="padding:8px 32px 8px 0">ESLint (jsx-a11y), tsc, vite build</td><td style="color:#4ade80;font-weight:700">clean</td></tr>
</table>
<p style="margin-top:28px;max-width:1000px">Frontend tests cover login, token refresh, logout, role-based navigation, creating a sale and the 409 on a retried completion. Backend tests cover RBAC, the transaction guarantee, caching, throttling, tasks and real concurrency.</p></body>`);
await caption("31 backend tests and 19 frontend tests, plus lint, typecheck and build, all in CI", 5000);

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
