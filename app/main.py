from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal, seed_roles
from app.routers import (
    auth,
    categories,
    damage,
    dashboard,
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        seed_roles(db)
    finally:
        db.close()
    yield


app = FastAPI(title="Inventra - Inventory Management System", lifespan=lifespan)

# Auth is Bearer-token only (no cookies), so allow_credentials stays False -
# that also means allow_origins=["*"] is valid CORS, not the browser-rejected
# "wildcard origin + credentials" combination. Real origins come from
# CORS_ALLOW_ORIGINS in production (see .env.example).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Rejects requests with a Host header that doesn't match ALLOWED_HOSTS,
# before they reach any route. Default "*" (dev) disables the check;
# production should set this to the real deployed domain(s).
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

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


@app.get("/health", tags=["health"])
def health_check():
    """Liveness + readiness in one: 200 only if the app is up AND can reach
    the database. Railway's healthcheck (see railway.json) polls this before
    routing traffic to a new deploy, and after every restart."""
    db_status = "ok"
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception:
        db_status = "error"

    body = {"status": "ok" if db_status == "ok" else "error", "database": db_status}
    status_code = status.HTTP_200_OK if db_status == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=body, status_code=status_code)


# serve the frontend (has to go last so it doesn't swallow the routes above)
frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
