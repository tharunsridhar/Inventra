"use strict";

/* ============================== config & state ============================== */

const API_BASE = ""; // same origin, FastAPI serves this file too

const state = {
  accessToken: localStorage.getItem("inventra_access") || null,
  refreshToken: localStorage.getItem("inventra_refresh") || null,
  user: null,
  view: "dashboard",
  categories: [],
  suppliers: [],
  products: [],
  page: {}, // per-view current page number
};

/* ============================== api layer ============================== */

async function api(path, { method = "GET", body, auth = true, query } = {}) {
  let url = API_BASE + path;
  if (query) {
    const qs = new URLSearchParams(
      Object.entries(query).filter(([, v]) => v !== undefined && v !== null && v !== "")
    ).toString();
    if (qs) url += "?" + qs;
  }

  const headers = { "Content-Type": "application/json" };
  if (auth && state.accessToken) headers.Authorization = "Bearer " + state.accessToken;

  const res = await fetch(url, { method, headers, body: body ? JSON.stringify(body) : undefined });

  if (res.status === 401 && auth && state.refreshToken) {
    const refreshed = await tryRefresh();
    if (refreshed) return api(path, { method, body, auth, query });
    logout();
    throw new Error("Session expired — please log in again");
  }

  if (res.status === 204) return null;

  let data = null;
  try {
    data = await res.json();
  } catch (_) {
    /* no body */
  }

  if (!res.ok) {
    // FastAPI puts errors in "detail" - either a plain string (our own
    // raise HTTPException calls) or a list of validation errors from pydantic
    let msg = `Request failed (${res.status})`;
    if (data && data.detail) {
      msg = typeof data.detail === "string" ? data.detail : data.detail.map((d) => d.msg).join(", ");
    }
    throw new Error(msg);
  }
  return data;
}

async function tryRefresh() {
  try {
    const res = await fetch(API_BASE + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });
    if (!res.ok) return false;
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token);
    return true;
  } catch (_) {
    return false;
  }
}

function setTokens(access, refresh) {
  state.accessToken = access;
  state.refreshToken = refresh;
  localStorage.setItem("inventra_access", access);
  localStorage.setItem("inventra_refresh", refresh);
}

function clearTokens() {
  state.accessToken = null;
  state.refreshToken = null;
  localStorage.removeItem("inventra_access");
  localStorage.removeItem("inventra_refresh");
}

/* ============================== ui helpers ============================== */

function toast(message, type = "info") {
  const el = document.createElement("div");
  el.className = "toast" + (type === "success" ? " toast-success" : type === "error" ? " toast-error" : "");
  el.textContent = message;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => el.remove(), 3500);
}

function openModal(title, bodyHtml, onMount) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = bodyHtml;
  document.getElementById("modal-backdrop").classList.remove("hidden");
  if (onMount) onMount(document.getElementById("modal-body"));
}
function closeModal() {
  document.getElementById("modal-backdrop").classList.add("hidden");
  document.getElementById("modal-body").innerHTML = "";
}

function money(v) {
  const n = Number(v);
  return "₹" + n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function dt(v) {
  if (!v) return "—";
  const d = new Date(v.endsWith("Z") ? v : v + "Z");
  return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}
function esc(s) {
  if (s === null || s === undefined) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function statusBadge(status) {
  const map = {
    ordered: "badge-warning", created: "badge-warning", pending: "badge-warning",
    received: "badge-success", completed: "badge-success", approved: "badge-success",
  };
  return `<span class="badge ${map[status] || "badge-primary"}">${esc(status)}</span>`;
}
function stockBadge(product) {
  if (product.current_stock <= 0) return '<span class="badge badge-danger">out of stock</span>';
  if (product.current_stock <= product.low_stock_threshold) return '<span class="badge badge-warning">low stock</span>';
  return '<span class="badge badge-success">in stock</span>';
}
function hasRole(...roles) {
  return state.user && roles.includes(state.user.role);
}

/* ============================== nav / router ============================== */

const VIEW_TITLES = {
  dashboard: "Dashboard", products: "Products", catalog: "Categories & Suppliers",
  purchases: "Purchase Orders", sales: "Sales Orders", returns: "Returns",
  damage: "Damage Write-off", transactions: "Inventory Transactions", reports: "Reports", users: "Users",
};

const VIEW_RENDERERS = {
  dashboard: renderDashboard, products: renderProducts, catalog: renderCatalog,
  purchases: renderPurchases, sales: renderSales, returns: renderReturns,
  damage: renderDamage, transactions: renderTransactions, reports: renderReports, users: renderUsers,
};

function showView(view) {
  state.view = view;
  document.querySelectorAll(".nav-item[data-view]").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === view);
  });
  document.getElementById("view-title").textContent = VIEW_TITLES[view] || view;
  const content = document.getElementById("content");
  content.innerHTML = '<div class="empty-state">Loading…</div>';
  VIEW_RENDERERS[view]().catch((err) => {
    content.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
  });
}

function applyRoleVisibility() {
  document.querySelectorAll(".nav-item[data-role]").forEach((btn) => {
    const allowed = btn.dataset.role.split(",");
    btn.classList.toggle("hidden", !hasRole(...allowed));
  });
}

/* ============================== auth ============================== */

async function login(email, password) {
  const data = await api("/auth/login", { method: "POST", body: { email, password }, auth: false });
  setTokens(data.access_token, data.refresh_token);
  await loadCurrentUser();
}

async function loadCurrentUser() {
  state.user = await api("/auth/me");
}

function logout() {
  const refresh = state.refreshToken;
  clearTokens();
  state.user = null;
  if (refresh) {
    fetch(API_BASE + "/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    }).catch(() => {});
  }
  document.getElementById("app-shell").classList.add("hidden");
  document.getElementById("login-screen").classList.remove("hidden");
}

function enterApp() {
  document.getElementById("login-screen").classList.add("hidden");
  document.getElementById("app-shell").classList.remove("hidden");
  document.getElementById("user-chip").textContent = `${state.user.full_name} · ${state.user.role}`;
  applyRoleVisibility();
  showView("dashboard");
  refreshNotifBadge();
}

/* ============================== dashboard ============================== */

async function renderDashboard() {
  const d = await api("/dashboard").catch(async (e) => {
    // Employee role isn't permitted; show a friendly limited view instead of an error.
    if (hasRole("employee")) return null;
    throw e;
  });
  const content = document.getElementById("content");
  if (!d) {
    content.innerHTML = `<div class="empty-state">Dashboard is available to Admin and Manager roles.<br/>Try the Products or Sales Orders views.</div>`;
    return;
  }
  const cards = [
    ["Products", d.total_products, ""],
    ["Categories", d.total_categories, ""],
    ["Suppliers", d.total_suppliers, ""],
    ["Users", d.total_users, ""],
    ["Purchase Orders", d.total_purchases, ""],
    ["Sales Orders", d.total_sales, ""],
    ["Low Stock", d.low_stock_products, "warn"],
    ["Out of Stock", d.out_of_stock_products, "danger"],
  ];
  content.innerHTML = `<div class="stat-grid">${cards
    .map(([label, value, cls]) => `
      <div class="stat-card ${cls}">
        <div class="stat-label">${label}</div>
        <div class="stat-value">${value}</div>
      </div>`).join("")}</div>`;
}

/* ============================== products ============================== */

async function loadRefData() {
  const [cats, sups] = await Promise.all([
    api("/categories", { query: { page_size: 100 } }),
    api("/suppliers", { query: { page_size: 100 } }),
  ]);
  state.categories = cats.items;
  state.suppliers = sups.items;
}

async function renderProducts() {
  if (state.categories.length === 0 || state.suppliers.length === 0) await loadRefData();
  const page = state.page.products || 1;
  const search = document.getElementById("prod-search")?.value || "";
  const stockStatus = document.getElementById("prod-stock-filter")?.value || "";

  const data = await api("/products", { query: { page, page_size: 10, search, stock_status: stockStatus } });
  const canManage = hasRole("admin", "manager");

  const catName = (id) => state.categories.find((c) => c.id === id)?.name || "—";
  const supName = (id) => state.suppliers.find((s) => s.id === id)?.name || "—";

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header">
        <h3>Products</h3>
        <div class="panel-toolbar">
          <input id="prod-search" type="text" placeholder="Search name, SKU, category, supplier…" value="${esc(search)}" />
          <select id="prod-stock-filter">
            <option value="">All stock</option>
            <option value="in_stock" ${stockStatus === "in_stock" ? "selected" : ""}>In stock</option>
            <option value="low_stock" ${stockStatus === "low_stock" ? "selected" : ""}>Low stock</option>
            <option value="out_of_stock" ${stockStatus === "out_of_stock" ? "selected" : ""}>Out of stock</option>
          </select>
          ${canManage ? `<button class="btn btn-primary btn-sm" id="new-product-btn">+ New product</button>` : ""}
        </div>
      </div>
      <div class="panel-body">
        <table>
          <thead><tr><th>SKU</th><th>Name</th><th>Category</th><th>Supplier</th><th>Cost</th><th>Price</th><th>Stock</th><th>Status</th>${canManage ? "<th></th>" : ""}</tr></thead>
          <tbody>
            ${data.items.length === 0 ? `<tr><td colspan="9" class="table-empty">No products found</td></tr>` : data.items.map((p) => `
              <tr>
                <td class="mono">${esc(p.sku)}</td>
                <td>${esc(p.name)}</td>
                <td>${esc(catName(p.category_id))}</td>
                <td>${esc(supName(p.supplier_id))}</td>
                <td>${money(p.cost_price)}</td>
                <td>${money(p.selling_price)}</td>
                <td>${p.current_stock}</td>
                <td>${stockBadge(p)}</td>
                ${canManage ? `<td class="row-actions">
                  <button class="btn btn-ghost btn-sm" data-edit-product="${p.id}">Edit</button>
                  <button class="btn btn-ghost btn-sm btn-danger" data-delete-product="${p.id}">Delete</button>
                </td>` : ""}
              </tr>`).join("")}
          </tbody>
        </table>
        ${pagination(data, "products")}
      </div>
    </div>`;

  document.getElementById("prod-search").addEventListener("change", () => { state.page.products = 1; renderProducts(); });
  document.getElementById("prod-stock-filter").addEventListener("change", () => { state.page.products = 1; renderProducts(); });
  document.getElementById("new-product-btn")?.addEventListener("click", () => openProductForm());
  document.querySelectorAll("[data-edit-product]").forEach((b) =>
    b.addEventListener("click", () => openProductForm(data.items.find((p) => p.id === b.dataset.editProduct))));
  document.querySelectorAll("[data-delete-product]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun(`Delete this product?`, () => api(`/products/${b.dataset.deleteProduct}`, { method: "DELETE" }), renderProducts)));
  bindPagination("products", renderProducts);
}

function optionList(items) {
  return items.map((i) => `<option value="${i.id}">${esc(i.name)}</option>`).join("");
}

function openProductForm(product) {
  const isEdit = !!product;
  openModal(isEdit ? "Edit product" : "New product", `
    <div class="form-grid">
      <label class="field">SKU <input id="f-sku" value="${esc(product?.sku || "")}" /></label>
      <label class="field">Name <input id="f-name" value="${esc(product?.name || "")}" /></label>
      <label class="field">Category <select id="f-category">${optionList(state.categories)}</select></label>
      <label class="field">Supplier <select id="f-supplier">${optionList(state.suppliers)}</select></label>
      <label class="field">Cost price <input id="f-cost" type="number" step="0.01" value="${product?.cost_price ?? ""}" /></label>
      <label class="field">Selling price <input id="f-price" type="number" step="0.01" value="${product?.selling_price ?? ""}" /></label>
      ${!isEdit ? `<label class="field">Initial stock <input id="f-stock" type="number" value="0" /></label>` : ""}
      <label class="field">Low stock threshold <input id="f-threshold" type="number" value="${product?.low_stock_threshold ?? 5}" /></label>
    </div>
    <label class="field" style="margin-top:14px">Description <textarea id="f-desc">${esc(product?.description || "")}</textarea></label>
    <div class="form-actions">
      <button class="btn" id="cancel-btn">Cancel</button>
      <button class="btn btn-primary" id="save-btn">${isEdit ? "Save changes" : "Create product"}</button>
    </div>`, (body) => {
    if (product) {
      body.querySelector("#f-category").value = product.category_id;
      body.querySelector("#f-supplier").value = product.supplier_id;
    }
    body.querySelector("#cancel-btn").addEventListener("click", closeModal);
    body.querySelector("#save-btn").addEventListener("click", async () => {
      const payload = {
        sku: body.querySelector("#f-sku").value.trim(),
        name: body.querySelector("#f-name").value.trim(),
        description: body.querySelector("#f-desc").value.trim() || null,
        category_id: body.querySelector("#f-category").value,
        supplier_id: body.querySelector("#f-supplier").value,
        cost_price: body.querySelector("#f-cost").value,
        selling_price: body.querySelector("#f-price").value,
        low_stock_threshold: Number(body.querySelector("#f-threshold").value),
      };
      if (!isEdit) payload.current_stock = Number(body.querySelector("#f-stock").value);
      try {
        if (isEdit) await api(`/products/${product.id}`, { method: "PATCH", body: payload });
        else await api("/products", { method: "POST", body: payload });
        closeModal();
        toast(isEdit ? "Product updated" : "Product created", "success");
        renderProducts();
      } catch (e) { toast(e.message, "error"); }
    });
  });
}

/* ============================== categories & suppliers ============================== */

async function renderCatalog() {
  const [cats, sups] = await Promise.all([
    api("/categories", { query: { page_size: 100 } }),
    api("/suppliers", { query: { page_size: 100 } }),
  ]);
  state.categories = cats.items;
  state.suppliers = sups.items;
  const canManage = hasRole("admin", "manager");

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>Categories</h3>${canManage ? `<button class="btn btn-primary btn-sm" id="new-cat-btn">+ New category</button>` : ""}</div>
      <div class="panel-body">
        <table><thead><tr><th>Name</th><th>Description</th>${canManage ? "<th></th>" : ""}</tr></thead>
        <tbody>${cats.items.length === 0 ? `<tr><td colspan="3" class="table-empty">No categories</td></tr>` : cats.items.map((c) => `
          <tr><td>${esc(c.name)}</td><td class="muted">${esc(c.description || "—")}</td>
          ${canManage ? `<td class="row-actions"><button class="btn btn-ghost btn-sm btn-danger" data-del-cat="${c.id}">Delete</button></td>` : ""}</tr>`).join("")}
        </tbody></table>
      </div>
    </div>
    <div class="panel">
      <div class="panel-header"><h3>Suppliers</h3>${canManage ? `<button class="btn btn-primary btn-sm" id="new-sup-btn">+ New supplier</button>` : ""}</div>
      <div class="panel-body">
        <table><thead><tr><th>Name</th><th>Email</th><th>Phone</th><th>Address</th>${canManage ? "<th></th>" : ""}</tr></thead>
        <tbody>${sups.items.length === 0 ? `<tr><td colspan="5" class="table-empty">No suppliers</td></tr>` : sups.items.map((s) => `
          <tr><td>${esc(s.name)}</td><td>${esc(s.email)}</td><td>${esc(s.phone || "—")}</td><td class="muted">${esc(s.address || "—")}</td>
          ${canManage ? `<td class="row-actions"><button class="btn btn-ghost btn-sm btn-danger" data-del-sup="${s.id}">Delete</button></td>` : ""}</tr>`).join("")}
        </tbody></table>
      </div>
    </div>`;

  document.getElementById("new-cat-btn")?.addEventListener("click", () => openModal("New category", `
    <label class="field">Name <input id="f-name" /></label>
    <label class="field" style="margin-top:12px">Description <textarea id="f-desc"></textarea></label>
    <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">Create</button></div>`,
    (body) => {
      body.querySelector("#cancel-btn").addEventListener("click", closeModal);
      body.querySelector("#save-btn").addEventListener("click", async () => {
        try {
          await api("/categories", { method: "POST", body: { name: body.querySelector("#f-name").value.trim(), description: body.querySelector("#f-desc").value.trim() || null } });
          closeModal(); toast("Category created", "success"); renderCatalog();
        } catch (e) { toast(e.message, "error"); }
      });
    }));

  document.getElementById("new-sup-btn")?.addEventListener("click", () => openModal("New supplier", `
    <div class="form-grid">
      <label class="field">Name <input id="f-name" /></label>
      <label class="field">Email <input id="f-email" type="email" /></label>
      <label class="field">Phone <input id="f-phone" /></label>
      <label class="field">Address <input id="f-address" /></label>
    </div>
    <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">Create</button></div>`,
    (body) => {
      body.querySelector("#cancel-btn").addEventListener("click", closeModal);
      body.querySelector("#save-btn").addEventListener("click", async () => {
        try {
          await api("/suppliers", { method: "POST", body: {
            name: body.querySelector("#f-name").value.trim(),
            email: body.querySelector("#f-email").value.trim(),
            phone: body.querySelector("#f-phone").value.trim() || null,
            address: body.querySelector("#f-address").value.trim() || null,
          }});
          closeModal(); toast("Supplier created", "success"); renderCatalog();
        } catch (e) { toast(e.message, "error"); }
      });
    }));

  document.querySelectorAll("[data-del-cat]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun("Delete this category?", () => api(`/categories/${b.dataset.delCat}`, { method: "DELETE" }), renderCatalog)));
  document.querySelectorAll("[data-del-sup]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun("Delete this supplier?", () => api(`/suppliers/${b.dataset.delSup}`, { method: "DELETE" }), renderCatalog)));
}

/* ============================== purchase orders ============================== */

async function renderPurchases() {
  if (state.products.length === 0) state.products = (await api("/products", { query: { page_size: 100 } })).items;
  if (state.suppliers.length === 0) state.suppliers = (await api("/suppliers", { query: { page_size: 100 } })).items;
  const canManage = hasRole("admin", "manager");
  if (!canManage) {
    document.getElementById("content").innerHTML = `<div class="empty-state">Purchase orders are managed by Admin and Manager roles.</div>`;
    return;
  }
  const page = state.page.purchases || 1;
  const data = await api("/purchase-orders", { query: { page, page_size: 10 } });
  const supName = (id) => state.suppliers.find((s) => s.id === id)?.name || "—";
  const prodName = (id) => state.products.find((p) => p.id === id)?.name || id;

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>Purchase Orders</h3><button class="btn btn-primary btn-sm" id="new-po-btn">+ New purchase order</button></div>
      <div class="panel-body">
        <table><thead><tr><th>Supplier</th><th>Items</th><th>Status</th><th>Created</th><th></th></tr></thead>
        <tbody>${data.items.length === 0 ? `<tr><td colspan="5" class="table-empty">No purchase orders</td></tr>` : data.items.map((po) => `
          <tr>
            <td>${esc(supName(po.supplier_id))}</td>
            <td class="muted">${po.items.map((i) => `${esc(prodName(i.product_id))} × ${i.quantity}`).join(", ")}</td>
            <td>${statusBadge(po.status)}</td>
            <td class="muted">${dt(po.created_at)}</td>
            <td class="row-actions">${po.status === "ordered" ? `<button class="btn btn-primary btn-sm" data-receive-po="${po.id}">Receive</button>` : ""}</td>
          </tr>`).join("")}
        </tbody></table>
        ${pagination(data, "purchases")}
      </div>
    </div>`;

  document.getElementById("new-po-btn").addEventListener("click", openPurchaseOrderForm);
  document.querySelectorAll("[data-receive-po]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun("Receive this purchase order? Stock will be increased.", () => api(`/purchase-orders/${b.dataset.receivePo}/receive`, { method: "POST" }), renderPurchases, "Purchase order received")));
  bindPagination("purchases", renderPurchases);
}

function lineItemRow(withCost) {
  return `<div class="line-item-row">
    <select class="li-product">${optionList(state.products)}</select>
    <input class="li-qty" type="number" min="1" placeholder="Qty" value="1" />
    ${withCost ? `<input class="li-price" type="number" step="0.01" placeholder="Unit cost" />` : `<span></span>`}
    <button type="button" class="btn btn-ghost btn-sm li-remove">✕</button>
  </div>`;
}

function bindLineItems(container, withCost) {
  const addRow = () => {
    const div = document.createElement("div");
    div.innerHTML = lineItemRow(withCost);
    const row = div.firstElementChild;
    row.querySelector(".li-remove").addEventListener("click", () => row.remove());
    container.appendChild(row);
  };
  addRow();
  return addRow;
}

function collectLineItems(container, withCost) {
  return Array.from(container.querySelectorAll(".line-item-row")).map((row) => {
    const item = { product_id: row.querySelector(".li-product").value, quantity: Number(row.querySelector(".li-qty").value) };
    if (withCost) item.unit_cost = row.querySelector(".li-price").value;
    return item;
  }).filter((i) => i.product_id && i.quantity > 0);
}

function openPurchaseOrderForm() {
  openModal("New purchase order", `
    <label class="field">Supplier <select id="f-supplier">${optionList(state.suppliers)}</select></label>
    <div class="section-title" style="margin-top:16px">Line items</div>
    <div class="line-items" id="line-items"></div>
    <button type="button" class="btn btn-ghost btn-sm" id="add-line" style="margin-top:8px">+ Add line item</button>
    <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">Create order</button></div>`,
    (body) => {
      const container = body.querySelector("#line-items");
      const addRow = bindLineItems(container, true);
      body.querySelector("#add-line").addEventListener("click", addRow);
      body.querySelector("#cancel-btn").addEventListener("click", closeModal);
      body.querySelector("#save-btn").addEventListener("click", async () => {
        const items = collectLineItems(container, true);
        if (items.length === 0) return toast("Add at least one line item", "error");
        try {
          await api("/purchase-orders", { method: "POST", body: { supplier_id: body.querySelector("#f-supplier").value, items } });
          closeModal(); toast("Purchase order created", "success"); renderPurchases();
        } catch (e) { toast(e.message, "error"); }
      });
    });
}

/* ============================== sales orders ============================== */

async function renderSales() {
  if (state.products.length === 0) state.products = (await api("/products", { query: { page_size: 100 } })).items;
  const page = state.page.sales || 1;
  const data = await api("/sales-orders", { query: { page, page_size: 10 } });
  const prodName = (id) => state.products.find((p) => p.id === id)?.name || id;

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>Sales Orders</h3><button class="btn btn-primary btn-sm" id="new-so-btn">+ New sale</button></div>
      <div class="panel-body">
        <table><thead><tr><th>Customer</th><th>Items</th><th>Status</th><th>Invoice</th><th>Created</th><th></th></tr></thead>
        <tbody>${data.items.length === 0 ? `<tr><td colspan="6" class="table-empty">No sales orders</td></tr>` : data.items.map((so) => `
          <tr>
            <td>${esc(so.customer_name || "—")}</td>
            <td class="muted">${so.items.map((i) => `${esc(prodName(i.product_id))} × ${i.quantity}`).join(", ")}</td>
            <td>${statusBadge(so.status)}</td>
            <td class="mono">${esc(so.invoice_number || "—")}</td>
            <td class="muted">${dt(so.created_at)}</td>
            <td class="row-actions">
              ${so.status === "created" ? `<button class="btn btn-primary btn-sm" data-complete-so="${so.id}">Complete</button>` : `<button class="btn btn-ghost btn-sm" data-view-invoice="${so.id}">Invoice</button>`}
            </td>
          </tr>`).join("")}
        </tbody></table>
        ${pagination(data, "sales")}
      </div>
    </div>`;

  document.getElementById("new-so-btn").addEventListener("click", openSalesOrderForm);
  document.querySelectorAll("[data-complete-so]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun("Complete this sale? Stock will be deducted.", () => api(`/sales-orders/${b.dataset.completeSo}/complete`, { method: "POST" }), renderSales, "Sale completed")));
  document.querySelectorAll("[data-view-invoice]").forEach((b) =>
    b.addEventListener("click", () => showInvoice(b.dataset.viewInvoice)));
  bindPagination("sales", renderSales);
}

async function showInvoice(soId) {
  try {
    const inv = await api(`/sales-orders/${soId}/invoice`);
    const prodName = (id) => state.products.find((p) => p.id === id)?.name || id;
    openModal(`Invoice ${inv.invoice_number}`, `
      <p class="muted">${esc(inv.customer_name || "Walk-in customer")} ${inv.customer_phone ? "· " + esc(inv.customer_phone) : ""}</p>
      <p class="muted">${dt(inv.invoiced_at)}</p>
      <table style="margin-top:12px"><thead><tr><th>Item</th><th>Qty</th><th>Unit price</th><th>Total</th></tr></thead>
      <tbody>${inv.items.map((i) => `<tr><td>${esc(prodName(i.product_id))}</td><td>${i.quantity}</td><td>${money(i.unit_price)}</td><td>${money(i.quantity * i.unit_price)}</td></tr>`).join("")}</tbody></table>
      <div class="form-actions" style="justify-content:space-between;align-items:center">
        <strong>Total: ${money(inv.total_amount)}</strong>
        <button class="btn" id="cancel-btn">Close</button>
      </div>`, (body) => body.querySelector("#cancel-btn").addEventListener("click", closeModal));
  } catch (e) { toast(e.message, "error"); }
}

function openSalesOrderForm() {
  openModal("New sale", `
    <div class="form-grid">
      <label class="field">Customer name <input id="f-cname" /></label>
      <label class="field">Customer phone <input id="f-cphone" /></label>
    </div>
    <div class="section-title" style="margin-top:16px">Line items</div>
    <div class="line-items" id="line-items"></div>
    <button type="button" class="btn btn-ghost btn-sm" id="add-line" style="margin-top:8px">+ Add line item</button>
    <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">Create sale</button></div>`,
    (body) => {
      const container = body.querySelector("#line-items");
      const addRow = bindLineItems(container, false);
      body.querySelector("#add-line").addEventListener("click", addRow);
      body.querySelector("#cancel-btn").addEventListener("click", closeModal);
      body.querySelector("#save-btn").addEventListener("click", async () => {
        const items = collectLineItems(container, false);
        if (items.length === 0) return toast("Add at least one line item", "error");
        try {
          await api("/sales-orders", { method: "POST", body: {
            customer_name: body.querySelector("#f-cname").value.trim() || null,
            customer_phone: body.querySelector("#f-cphone").value.trim() || null,
            items,
          }});
          closeModal(); toast("Sales order created", "success"); renderSales();
        } catch (e) { toast(e.message, "error"); }
      });
    });
}

/* ============================== returns ============================== */

async function renderReturns() {
  if (state.products.length === 0) state.products = (await api("/products", { query: { page_size: 100 } })).items;
  const page = state.page.returns || 1;
  const data = await api("/returns", { query: { page, page_size: 10 } });
  const prodName = (id) => state.products.find((p) => p.id === id)?.name || id;

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>Returns</h3><button class="btn btn-primary btn-sm" id="new-ret-btn">+ File return</button></div>
      <div class="panel-body">
        <table><thead><tr><th>Sales order</th><th>Product</th><th>Qty</th><th>Reason</th><th>Status</th><th></th></tr></thead>
        <tbody>${data.items.length === 0 ? `<tr><td colspan="6" class="table-empty">No returns filed</td></tr>` : data.items.map((r) => `
          <tr>
            <td class="mono">${r.sales_order_id.slice(0, 8)}…</td>
            <td>${esc(prodName(r.product_id))}</td>
            <td>${r.quantity}</td>
            <td class="muted">${esc(r.reason)}</td>
            <td>${statusBadge(r.status)}</td>
            <td class="row-actions">${r.status === "pending" ? `<button class="btn btn-primary btn-sm" data-approve-ret="${r.id}">Approve</button>` : ""}</td>
          </tr>`).join("")}
        </tbody></table>
        ${pagination(data, "returns")}
      </div>
    </div>`;

  document.getElementById("new-ret-btn").addEventListener("click", () => openModal("File a return", `
    <div class="form-grid single">
      <label class="field">Sales order ID <input id="f-so" placeholder="Paste the sales order ID" /></label>
      <label class="field">Product <select id="f-product">${optionList(state.products)}</select></label>
      <label class="field">Quantity <input id="f-qty" type="number" min="1" value="1" /></label>
      <label class="field">Reason <textarea id="f-reason" placeholder="Why is this being returned?"></textarea></label>
    </div>
    <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">File return</button></div>`,
    (body) => {
      body.querySelector("#cancel-btn").addEventListener("click", closeModal);
      body.querySelector("#save-btn").addEventListener("click", async () => {
        try {
          await api("/returns", { method: "POST", body: {
            sales_order_id: body.querySelector("#f-so").value.trim(),
            product_id: body.querySelector("#f-product").value,
            quantity: Number(body.querySelector("#f-qty").value),
            reason: body.querySelector("#f-reason").value.trim(),
          }});
          closeModal(); toast("Return filed", "success"); renderReturns();
        } catch (e) { toast(e.message, "error"); }
      });
    }));

  document.querySelectorAll("[data-approve-ret]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun("Approve this return? Stock will be increased.", () => api(`/returns/${b.dataset.approveRet}/approve`, { method: "PATCH" }), renderReturns, "Return approved")));
  bindPagination("returns", renderReturns);
}

/* ============================== damage write-off ============================== */

async function renderDamage() {
  if (state.products.length === 0) state.products = (await api("/products", { query: { page_size: 100 } })).items;
  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>Log a damage write-off</h3></div>
      <div class="panel-body">
        <div class="form-grid">
          <label class="field">Product <select id="f-product">${optionList(state.products)}</select></label>
          <label class="field">Quantity <input id="f-qty" type="number" min="1" value="1" /></label>
        </div>
        <label class="field" style="margin-top:14px">Reason (required) <textarea id="f-reason" placeholder="e.g. water damage in warehouse"></textarea></label>
        <div class="form-actions"><button class="btn btn-primary" id="save-btn">Write off stock</button></div>
      </div>
    </div>
    <div class="section-title">Recent damage transactions</div>
    <div id="damage-list"></div>`;

  document.getElementById("save-btn").addEventListener("click", async () => {
    const reason = document.getElementById("f-reason").value.trim();
    if (!reason) return toast("A reason is required", "error");
    try {
      await api("/damage", { method: "POST", body: {
        product_id: document.getElementById("f-product").value,
        quantity: Number(document.getElementById("f-qty").value),
        reason,
      }});
      toast("Damage write-off recorded", "success");
      document.getElementById("f-reason").value = "";
      loadRecentDamage();
    } catch (e) { toast(e.message, "error"); }
  });
  loadRecentDamage();
}

async function loadRecentDamage() {
  const data = await api("/inventory-transactions", { query: { transaction_type: "damage", page_size: 10 } });
  const prodName = (id) => state.products.find((p) => p.id === id)?.name || id;
  document.getElementById("damage-list").innerHTML = `
    <div class="panel"><div class="panel-body">
      <table><thead><tr><th>Product</th><th>Qty</th><th>Reason</th><th>When</th></tr></thead>
      <tbody>${data.items.length === 0 ? `<tr><td colspan="4" class="table-empty">No damage logged yet</td></tr>` : data.items.map((t) => `
        <tr><td>${esc(prodName(t.product_id))}</td><td>${t.quantity}</td><td class="muted">${esc(t.reason || "—")}</td><td class="muted">${dt(t.created_at)}</td></tr>`).join("")}
      </tbody></table>
    </div></div>`;
}

/* ============================== inventory transactions ============================== */

async function renderTransactions() {
  if (state.products.length === 0) state.products = (await api("/products", { query: { page_size: 100 } })).items;
  const canView = hasRole("admin", "manager");
  if (!canView) {
    document.getElementById("content").innerHTML = `<div class="empty-state">Transaction history is available to Admin and Manager roles.</div>`;
    return;
  }
  const page = state.page.transactions || 1;
  const type = document.getElementById("txn-type-filter")?.value || "";
  const data = await api("/inventory-transactions", { query: { page, page_size: 15, transaction_type: type } });
  const prodName = (id) => state.products.find((p) => p.id === id)?.name || id;

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header">
        <h3>Inventory Transactions</h3>
        <div class="panel-toolbar">
          <select id="txn-type-filter">
            <option value="">All types</option>
            <option value="purchase" ${type === "purchase" ? "selected" : ""}>Purchase</option>
            <option value="sale" ${type === "sale" ? "selected" : ""}>Sale</option>
            <option value="return" ${type === "return" ? "selected" : ""}>Return</option>
            <option value="damage" ${type === "damage" ? "selected" : ""}>Damage</option>
          </select>
        </div>
      </div>
      <div class="panel-body">
        <table><thead><tr><th>Product</th><th>Type</th><th>Qty</th><th>Reason</th><th>When</th></tr></thead>
        <tbody>${data.items.length === 0 ? `<tr><td colspan="5" class="table-empty">No transactions</td></tr>` : data.items.map((t) => `
          <tr><td>${esc(prodName(t.product_id))}</td><td>${statusBadge(t.transaction_type)}</td><td>${t.quantity}</td><td class="muted">${esc(t.reason || "—")}</td><td class="muted">${dt(t.created_at)}</td></tr>`).join("")}
        </tbody></table>
        ${pagination(data, "transactions")}
      </div>
    </div>`;
  document.getElementById("txn-type-filter").addEventListener("change", () => { state.page.transactions = 1; renderTransactions(); });
  bindPagination("transactions", renderTransactions);
}

/* ============================== reports ============================== */

async function renderReports() {
  if (!hasRole("admin", "manager")) {
    document.getElementById("content").innerHTML = `<div class="empty-state">Reports are available to Admin and Manager roles.</div>`;
    return;
  }
  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header">
        <h3>Reports</h3>
        <div class="panel-toolbar">
          <select id="report-type">
            <option value="products">Product report</option>
            <option value="purchases">Purchase report</option>
            <option value="sales">Sales report</option>
            <option value="inventory">Inventory report</option>
          </select>
          <input type="date" id="report-start" />
          <input type="date" id="report-end" />
          <button class="btn btn-primary btn-sm" id="run-report">Run</button>
        </div>
      </div>
      <div class="panel-body" id="report-output"><div class="empty-state">Choose a report and click Run</div></div>
    </div>`;
  document.getElementById("run-report").addEventListener("click", runReport);
}

async function runReport() {
  const type = document.getElementById("report-type").value;
  const start = document.getElementById("report-start").value;
  const end = document.getElementById("report-end").value;
  const query = {};
  if (start) query.start_date = start + "T00:00:00";
  if (end) query.end_date = end + "T23:59:59";
  const out = document.getElementById("report-output");
  out.innerHTML = `<div class="empty-state">Loading…</div>`;
  try {
    const data = await api(`/reports/${type}`, { query });
    out.innerHTML = `<pre class="mono" style="white-space:pre-wrap;background:#fafafe;padding:14px;border-radius:8px;max-height:480px;overflow:auto">${esc(JSON.stringify(data, null, 2))}</pre>`;
  } catch (e) {
    out.innerHTML = `<div class="empty-state">${esc(e.message)}</div>`;
  }
}

/* ============================== users ============================== */

const ROLE_OPTIONS = ["admin", "manager", "employee"];

async function renderUsers() {
  if (!hasRole("admin")) {
    document.getElementById("content").innerHTML = `<div class="empty-state">User management is Admin-only.</div>`;
    return;
  }
  const page = state.page.users || 1;
  const data = await api("/users", { query: { page, page_size: 10 } });

  document.getElementById("content").innerHTML = `
    <div class="panel">
      <div class="panel-header"><h3>Users</h3><button class="btn btn-primary btn-sm" id="new-user-btn">+ New user</button></div>
      <div class="panel-body">
        <table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th></th></tr></thead>
        <tbody>${data.items.map((u) => `
          <tr>
            <td>${esc(u.full_name)}</td>
            <td>${esc(u.email)}</td>
            <td><select class="role-select" data-user="${u.id}">${ROLE_OPTIONS.map((r) => `<option value="${r}" ${r === u.role ? "selected" : ""}>${r}</option>`).join("")}</select></td>
            <td>${u.is_active ? '<span class="badge badge-success">active</span>' : '<span class="badge badge-danger">disabled</span>'}</td>
            <td class="row-actions">
              ${u.is_active ? `<button class="btn btn-ghost btn-sm btn-danger" data-disable="${u.id}">Disable</button>` : `<button class="btn btn-ghost btn-sm" data-enable="${u.id}">Enable</button>`}
              <button class="btn btn-ghost btn-sm" data-reset="${u.id}">Reset password</button>
            </td>
          </tr>`).join("")}
        </tbody></table>
        ${pagination(data, "users")}
      </div>
    </div>`;

  document.getElementById("new-user-btn").addEventListener("click", () => openModal("New user", `
    <div class="form-grid">
      <label class="field">Full name <input id="f-name" /></label>
      <label class="field">Email <input id="f-email" type="email" /></label>
      <label class="field">Password <input id="f-password" type="password" /></label>
      <label class="field">Role <select id="f-role">${ROLE_OPTIONS.map((r) => `<option value="${r}">${r}</option>`).join("")}</select></label>
    </div>
    <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">Create</button></div>`,
    (body) => {
      body.querySelector("#cancel-btn").addEventListener("click", closeModal);
      body.querySelector("#save-btn").addEventListener("click", async () => {
        try {
          await api("/users", { method: "POST", body: {
            full_name: body.querySelector("#f-name").value.trim(),
            email: body.querySelector("#f-email").value.trim(),
            password: body.querySelector("#f-password").value,
            role: body.querySelector("#f-role").value,
          }});
          closeModal(); toast("User created", "success"); renderUsers();
        } catch (e) { toast(e.message, "error"); }
      });
    }));

  document.querySelectorAll(".role-select").forEach((sel) => {
    sel.addEventListener("change", async () => {
      try {
        await api(`/users/${sel.dataset.user}/role`, { method: "PATCH", body: { role: sel.value } });
        toast("Role updated", "success");
      } catch (e) { toast(e.message, "error"); renderUsers(); }
    });
  });
  document.querySelectorAll("[data-disable]").forEach((b) =>
    b.addEventListener("click", () => confirmAndRun("Disable this user?", () => api(`/users/${b.dataset.disable}`, { method: "DELETE" }), renderUsers)));
  document.querySelectorAll("[data-enable]").forEach((b) =>
    b.addEventListener("click", () => api(`/users/${b.dataset.enable}/enable`, { method: "PATCH" }).then(renderUsers).then(() => toast("User enabled", "success")).catch((e) => toast(e.message, "error"))));
  document.querySelectorAll("[data-reset]").forEach((b) =>
    b.addEventListener("click", () => openModal("Reset password", `
      <label class="field">New password <input id="f-pw" type="password" /></label>
      <div class="form-actions"><button class="btn" id="cancel-btn">Cancel</button><button class="btn btn-primary" id="save-btn">Reset</button></div>`,
      (body) => {
        body.querySelector("#cancel-btn").addEventListener("click", closeModal);
        body.querySelector("#save-btn").addEventListener("click", async () => {
          try {
            await api(`/users/${b.dataset.reset}/reset-password`, { method: "PATCH", body: { new_password: body.querySelector("#f-pw").value } });
            closeModal(); toast("Password reset", "success");
          } catch (e) { toast(e.message, "error"); }
        });
      })));
  bindPagination("users", renderUsers);
}

/* ============================== notifications ============================== */

async function refreshNotifBadge() {
  try {
    const data = await api("/notifications", { query: { unread_only: true, page_size: 1 } });
    const badge = document.getElementById("notif-badge");
    if (data.total > 0) { badge.textContent = data.total; badge.classList.remove("hidden"); }
    else badge.classList.add("hidden");
  } catch (_) { /* silent */ }
}

async function openNotifDrawer() {
  document.getElementById("notif-drawer").classList.remove("hidden");
  document.getElementById("drawer-backdrop").classList.remove("hidden");
  const list = document.getElementById("notif-list");
  list.innerHTML = `<div class="empty-state">Loading…</div>`;
  const data = await api("/notifications", { query: { page_size: 30 } });
  list.innerHTML = data.items.length === 0 ? `<div class="empty-state">No notifications yet</div>` : data.items.map((n) => `
    <div class="notif-item ${n.is_read ? "" : "unread"}" data-notif="${n.id}">
      <div class="notif-msg">${esc(n.message)}</div>
      <div class="notif-meta">${n.type.replace(/_/g, " ")} · ${dt(n.created_at)}</div>
    </div>`).join("");
  list.querySelectorAll("[data-notif]").forEach((el) =>
    el.addEventListener("click", async () => {
      await api(`/notifications/${el.dataset.notif}/read`, { method: "PATCH" }).catch(() => {});
      el.classList.remove("unread");
      refreshNotifBadge();
    }));
}
function closeNotifDrawer() {
  document.getElementById("notif-drawer").classList.add("hidden");
  document.getElementById("drawer-backdrop").classList.add("hidden");
}

/* ============================== shared widgets ============================== */

function pagination(data, key) {
  const totalPages = Math.max(1, Math.ceil(data.total / data.page_size));
  return `<div class="pagination">
    <span>Page ${data.page} of ${totalPages} · ${data.total} total</span>
    <button class="btn btn-sm" id="pg-prev" ${data.page <= 1 ? "disabled" : ""}>← Prev</button>
    <button class="btn btn-sm" id="pg-next" ${data.page >= totalPages ? "disabled" : ""}>Next →</button>
  </div>`;
}
function bindPagination(key, renderer) {
  document.getElementById("pg-prev")?.addEventListener("click", () => { state.page[key] = (state.page[key] || 1) - 1; renderer(); });
  document.getElementById("pg-next")?.addEventListener("click", () => { state.page[key] = (state.page[key] || 1) + 1; renderer(); });
}
function confirmAndRun(message, action, renderer, successMsg) {
  openModal("Please confirm", `
    <p>${esc(message)}</p>
    <div class="form-actions">
      <button class="btn" id="cancel-btn">Cancel</button>
      <button class="btn btn-primary" id="confirm-btn">Confirm</button>
    </div>`, (body) => {
    body.querySelector("#cancel-btn").addEventListener("click", closeModal);
    body.querySelector("#confirm-btn").addEventListener("click", async () => {
      closeModal();
      try {
        await action();
        toast(successMsg || "Done", "success");
        renderer();
      } catch (e) {
        toast(e.message, "error");
      }
    });
  });
}

/* ============================== bootstrap ============================== */

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");
  errorEl.classList.add("hidden");
  try {
    await login(email, password);
    enterApp();
  } catch (err) {
    errorEl.textContent = err.message;
    errorEl.classList.remove("hidden");
  }
});

document.getElementById("logout-btn").addEventListener("click", logout);
document.getElementById("notif-btn").addEventListener("click", openNotifDrawer);
document.getElementById("notif-close").addEventListener("click", closeNotifDrawer);
document.getElementById("drawer-backdrop").addEventListener("click", closeNotifDrawer);
document.getElementById("modal-close").addEventListener("click", closeModal);
document.getElementById("modal-backdrop").addEventListener("click", (e) => { if (e.target.id === "modal-backdrop") closeModal(); });
document.querySelectorAll(".nav-item[data-view]").forEach((btn) => btn.addEventListener("click", () => showView(btn.dataset.view)));

(async function init() {
  if (state.accessToken) {
    try {
      await loadCurrentUser();
      enterApp();
      return;
    } catch (_) {
      clearTokens();
    }
  }
  document.getElementById("login-screen").classList.remove("hidden");
})();
