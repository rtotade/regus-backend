"""
RegWatch Nexus — Main FastAPI Application
Open public platform with optional subscription tiers
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

from backend.config import settings
from backend.database import init_db, close_db
from backend.api.public import router as public_router
from backend.api.auth import router as auth_router
from backend.api.alerts import router as alerts_router
from backend.api.intelligence import router as intelligence_router
from backend.api.dashboard import router as dashboard_router
from backend.api.actions import router as actions_router
from backend.api.reports import router as reports_router
from backend.api.counsel import router as counsel_router
from backend.api.webhooks import router as webhooks_router
from backend.api.admin import router as admin_router
from backend.scheduler import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await start_scheduler()
    yield
    await stop_scheduler()
    await close_db()


app = FastAPI(
    title="RegWatch Nexus API",
    description="Global Regulatory & Compliance Intelligence Platform",
    version="7.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.include_router(public_router,       prefix="/api/v1",           tags=["Public"])
app.include_router(auth_router,         prefix="/api/v1/auth",      tags=["Auth"])
app.include_router(alerts_router,       prefix="/api/v1/alerts",    tags=["Alerts"])
app.include_router(intelligence_router, prefix="/api/v1/intel",     tags=["Intelligence"])
app.include_router(dashboard_router,    prefix="/api/v1/dashboard", tags=["Dashboard"])
app.include_router(actions_router,      prefix="/api/v1/actions",   tags=["Actions"])
app.include_router(reports_router,      prefix="/api/v1/reports",   tags=["Reports"])
app.include_router(counsel_router,      prefix="/api/v1/counsel",   tags=["Counsel"])
app.include_router(webhooks_router,     prefix="/api/v1/webhooks",  tags=["Webhooks"])
app.include_router(admin_router,        prefix="/api/v1/admin",     tags=["Admin"])

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


@app.get("/{full_path:path}", response_class=HTMLResponse, include_in_schema=False)
async def serve_frontend(full_path: str, request: Request):
    page_map = {
        "": "index", "alerts": "alerts", "intelligence": "intelligence",
        "regulators": "regulators", "countries": "countries", "reports": "reports",
        "search": "search", "pricing": "pricing", "register": "register",
        "login": "login", "dashboard": "dashboard", "actions": "actions",
        "policies": "policies", "counsel": "counsel", "workspace": "workspace",
        "account": "account",
    }
    first_segment = full_path.split("/")[0] if full_path else ""
    if first_segment == "alerts" and "/" in full_path:
        page = "alert_detail"
    elif first_segment == "regulators" and "/" in full_path:
        page = "regulator_detail"
    elif first_segment == "countries" and "/" in full_path:
        page = "country_detail"
    else:
        page = page_map.get(first_segment, "index")
    
    page_file = f"frontend/pages/{page}.html"
    fallback = "frontend/pages/index.html"
    target = page_file if os.path.exists(page_file) else fallback
    with open(target) as f:
        return HTMLResponse(f.read())


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0",
                port=int(os.getenv("PORT", 8000)),
                reload=settings.DEBUG, workers=1 if settings.DEBUG else 4)
