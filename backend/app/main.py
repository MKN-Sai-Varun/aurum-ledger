from fastapi import FastAPI

from app.config import load_settings

settings = load_settings()

# API documentation pages are switched off in production.
app = FastAPI(
    title="Karigar Gold Ledger API",
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/openapi.json",
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}