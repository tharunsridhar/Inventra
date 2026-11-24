// Records the Inventra demo against a locally running stack (docker compose up) that has
// been seeded with `manage.py seed_demo` (demo logins, password demopass123).
//
//   DEMO_URL=http://localhost:8000 node record.mjs
//
// Output: inventra-demo.webm and frames/NN.png (key frames used by make_gif.py).
// The UI scenes are live. The last scene is a card quoting the recorded load-test
// results from docs/v2/LOAD_TEST_RESULTS.md; it does not re-run Locust.
import { chromium } from "playwright";
import { mkdirSync, rmSync, renameSync, readdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const BASE = process.env.DEMO_URL ?? "http://localhost:8000";
const EMAIL = "demo-manager-1@demo.seed";
const PASSWORD = "demopass123";
const W = 1280;
const H = 720;
const customer = "Demo Customer " + new Date().toISOString().slice(11, 19);

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
const nav = async (view) => {
  await page.locator(`button[data-view="${view}"]`).click();
  await page.waitForTimeout(900);
};

// Pick a product with plenty of stock, via the API, so the sale cannot fail on stock.
const api = await ctx.request.post(`${BASE}/auth/login`, { data: { email: EMAIL, password: PASSWORD } });
if (!api.ok()) throw new Error(`login failed: ${api.status()}; seed the demo data first`);
const { access } = await api.json();
const prods = await (
  await ctx.request.get(`${BASE}/products/?page_size=100`, { headers: { Authorization: `Bearer ${access}` } })
).json();
const product = prods.results.find((p) => p.current_stock >= 20 && !String(p.sku).startsWith("LOADTEST"));
if (!product) throw new Error("no product with enough stock found");

// Scene 1: sign in
await page.goto(BASE + "/app");
await page.locator("#login-email").fill(EMAIL);
await page.locator("#login-password").fill(PASSWORD);
await caption("Inventra: inventory backend with role-based login (Manager)");
await page.getByRole("button", { name: "Sign in" }).click();
await page.locator("#app-shell:not(.hidden)").waitFor();
await page.waitForTimeout(1200);
await caption("Dashboard: live stock, orders and low-stock alerts");

// Scene 2: products
await nav("products");
await caption(`Products: ${product.name} has ${product.current_stock} units in stock`);

// Scene 3: create a sale
await nav("sales");
await page.locator("#new-so-btn").click();
await page.locator("#f-cname").fill(customer);
await page.locator(".li-product").first().selectOption({ value: String(product.id) });
await page.locator(".li-qty").first().fill("3");
await caption("New sale: 3 units for a customer");
await page.locator("#save-btn").click();
await page.waitForTimeout(1000);

// Scene 4: complete it (stock is deducted atomically, under a row lock)
const row = page.locator("tr", { hasText: customer });
await row.locator("[data-complete-so]").click();
await caption("Completing the sale deducts stock inside a database transaction");
await page.locator("#confirm-btn").click();
await page.waitForTimeout(1200);
await caption("Sale completed, invoice number issued");

// Scene 5: the append-only ledger
await nav("transactions");
await page.locator("#txn-type-filter").selectOption("sale");
await page.waitForTimeout(900);
await caption("Every stock change is an append-only ledger row; nothing can edit or delete it", 3200);

// Scene 6: recorded load-test results (static card, sourced from the repo docs)
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
