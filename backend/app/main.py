from fastapi import FastAPI, Request

from app.config import load_settings
from app.routers.auth import router as auth_router
from app.routers.corrections import router as corrections_router
from app.routers.jobs import router as jobs_router
from app.routers.karigars import router as karigars_router
from app.routers.ledger import router as ledger_router

settings = load_settings()

# API documentation pages are switched off in production.
app = FastAPI(
    title="Aurum API",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(auth_router)
app.include_router(karigars_router)
app.include_router(ledger_router)
app.include_router(jobs_router)
app.include_router(corrections_router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}