from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.idempotency import Replay

from app.bootstrap import bootstrap
from app.routers.alerts import router as alerts_router
from app.routers.auth import router as auth_router
from app.routers.corrections import router as corrections_router
from app.routers.jobs import router as jobs_router
from app.routers.karigars import router as karigars_router
from app.routers.ledger import router as ledger_router
from app.routers.readings import router as readings_router
from app.routers.stock import router as stock_router
from app.routers.old_gold import router as old_gold_router
from app.db import settings

# The built frontend, present only inside the container image.
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    bootstrap()
    yield


# API documentation pages are switched off in production.
app = FastAPI(
    title="Aurum API",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
    lifespan=lifespan,
)

@app.exception_handler(Replay)
async def replay_handler(_request: Request, exc: Replay):
    return JSONResponse(
        exc.payload, status_code=201, headers={"Idempotent-Replay": "true"}
    )

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    if settings.is_production:
        response.headers.setdefault("Content-Security-Policy", CSP)
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
    return response


app.include_router(auth_router)
app.include_router(karigars_router)
app.include_router(ledger_router)
app.include_router(jobs_router)
app.include_router(corrections_router)
app.include_router(alerts_router)
app.include_router(stock_router)
app.include_router(readings_router)
app.include_router(old_gold_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# Mounted last, so every /api route above takes precedence.
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="web")