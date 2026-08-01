# Inventra — Inventory Management System

A college-project-style Inventory Management System: FastAPI + SQLAlchemy 2.0 + SQLite backend,
plain HTML/CSS/JS frontend, no fancy layering — just routers, models, schemas, and a database
file. Single-warehouse, single-currency (INR), JWT login, and a stock movement history that's
never edited or deleted.

## Project structure

```
app/
  main.py       - creates the FastAPI app, includes all the routers, serves the frontend
  config.py     - reads settings from .env
  database.py   - SQLAlchemy engine/session + get_db()
  models.py     - every SQLAlchemy table
  schemas.py    - every Pydantic request/response model
  auth.py       - password hashing, JWT, get_current_user / require_role
  utils.py      - a couple of small helpers (datetime, notifications)
  routers/      - one file per resource (auth, users, products, sales, ...)
alembic/        - migrations
frontend/       - index.html + styles.css + app.js
seed.py         - demo data
```

No repository/service layers — each router talks to the database directly with plain
SQLAlchemy queries, the way most course projects do it.

## Tech stack

FastAPI · SQLAlchemy 2.0 · SQLite · Alembic · JWT (access + DB-stored revocable refresh tokens) · bcrypt · Pydantic v2
Frontend: plain HTML/CSS/JS, no build step, no framework — served directly by FastAPI.

## Setup

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run python seed.py
uv run uvicorn app.main:app --reload
```

Everything is served from **one** origin: **http://127.0.0.1:8000**

- `/` — the frontend (login screen and app)
- `/auth`, `/products`, `/sales-orders`, etc. — the REST API (no version prefix)
- `/docs` — interactive Swagger UI

## Demo credentials (from `seed.py`)

| Role     | Email                    | Password     |
|----------|---------------------------|---------------|
| Admin    | admin@inventra.com        | admin123      |
| Manager  | manager@inventra.com      | manager123    |
| Employee | employee@inventra.com     | employee123   |

Open `http://127.0.0.1:8000` and log in with any of the accounts above — the UI adapts to
the role (Employee doesn't see Users/Returns/Damage/Reports, etc.).

Or drive the API directly: log in via `POST /auth/login`, then pass the returned
`access_token` as `Authorization: Bearer <token>`.

## Frontend

`frontend/index.html` + `styles.css` + `app.js` — no build step, no framework. FastAPI mounts
the `frontend/` directory as static files at `/` (see `app/main.py`), so the UI and API are
same-origin; `app.js` talks to the API via relative paths like `/auth/login`. Covers the full golden
path: login, dashboard, products (search/filter/sort/CRUD), categories/suppliers, purchase
orders (create/receive), sales orders (create/complete/invoice), returns, damage write-off,
transaction history, reports, notifications, and admin user management — with nav items and
actions hidden per the logged-in role.

## Roles & permissions

- **Admin** — full access, including user management.
- **Manager** — products, suppliers, categories, purchases, sales, approves returns, logs damage, views reports/dashboard.
- **Employee** — views products/inventory, creates and completes sales orders only.

## Core business flow

```
Supplier → Purchase Order (ordered) → /receive → Product.current_stock +=
Customer → Sales Order (created)    → /complete → Product.current_stock -=
Sales Order (completed) → Return (pending) → Manager /approve → Product.current_stock +=
Manager/Admin → Damage write-off (reason required) → Product.current_stock -=
```

Every stock-affecting action writes exactly one immutable `InventoryTransaction` row
(`purchase` / `sale` / `return` / `damage`) — there is no update or delete route for
this resource. Receiving a purchase order and completing a sales order are each a
single atomic DB transaction and are idempotent: calling either a second time on an
already-`received`/`completed` order returns `409 Conflict` with no side effects.

## Key endpoints

See `/docs` for the full interactive schema.

- `auth`: register, login, refresh, logout, me
- `users` (Admin only): CRUD, assign-role, reset-password, enable/disable
- `categories`, `suppliers`, `products`: CRUD + soft delete, search/filter/sort/pagination on products
- `purchase-orders`: create, update (pre-receive only), receive
- `sales-orders`: create, update (pre-complete only), complete, invoice
- `returns`: create, approve (Manager/Admin)
- `damage`: write-off (Manager/Admin, reason required)
- `inventory-transactions`: read-only, filterable by product/type/date range
- `dashboard`: aggregate counts and low/out-of-stock indicators
- `reports`: products / purchases / sales / inventory, JSON, date-range filterable
- `notifications`: per-user, filterable by unread, mark-as-read

## Design notes / deliberate defaults

A few points were left implicit in the original spec and resolved as follows:

- Sales lifecycle is two-step, symmetric with purchase orders: `POST /sales-orders`
  creates a `created` order (no stock check yet); `PATCH /sales-orders/{id}/complete`
  validates stock, deducts it, writes the transaction, and generates the invoice —
  all in one atomic, idempotent transaction.
- `POST /auth/register` always creates an Employee account; only an Admin can
  promote a user via `PATCH /users/{id}/role`.
- There is no separate `invoices` table (not in the spec's finalized table list) —
  the completed sales order itself carries `invoice_number` / `invoiced_at`.
- Damage write-offs reuse `inventory_transactions.reason` (nullable, populated
  only for damage rows) rather than a dedicated damage table, for the same reason.
- A return reserves its quantity against the sold amount as soon as it's filed
  (not only once approved), so two pending returns can't later both be approved
  and jointly exceed what was actually sold.

## Deferred to v2+

Multi-warehouse support, partial PO receiving, PO approval workflow, supplier
returns, PDF invoices/reports, email-based password reset/notifications, refresh
token rotation, extensible RBAC, rate limiting, structured logging, automated
test suite, Docker/Redis/cloud deployment/file storage.
