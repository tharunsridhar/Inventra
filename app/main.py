from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import SessionLocal, seed_roles
from app.routers import (
    auth,
    categories,
    dashboard,
    damage,
    notifications,
    products,
    purchases,
    reports,
    returns,
    sales,
    suppliers,
    transactions,
    users,
)

app = FastAPI(title="Inventra - Inventory Management System")

# allow everything for local dev, this isn't going to prod
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(suppliers.router)
app.include_router(products.router)
app.include_router(purchases.router)
app.include_router(sales.router)
app.include_router(returns.router)
app.include_router(damage.router)
app.include_router(transactions.router)
app.include_router(dashboard.router)
app.include_router(reports.router)
app.include_router(notifications.router)


@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        seed_roles(db)
    finally:
        db.close()


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}


# serve the frontend (has to go last so it doesn't swallow the routes above)
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
