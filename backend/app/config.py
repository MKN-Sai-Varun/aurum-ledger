"""Application settings, read from environment variables.

Secrets are never stored in the repository. In production the app
refuses to start with a missing or weak signing secret.
"""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_MIN_SECRET_LENGTH = 32
_DEV_FALLBACK_SECRET = "dev-only-secret-not-for-production-use"


@dataclass(frozen=True)
class Settings:
    app_env: str
    database_url: str
    jwt_secret: str
    gemini_api_key: str

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def load_settings() -> Settings:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    jwt_secret = os.getenv("JWT_SECRET", "").strip()

    if app_env == "production":
        if len(jwt_secret) < _MIN_SECRET_LENGTH:
            raise RuntimeError(
                "JWT_SECRET must be set to at least 32 characters in production."
            )
    elif not jwt_secret:
        jwt_secret = _DEV_FALLBACK_SECRET

    return Settings(
        app_env=app_env,
        database_url=os.getenv("DATABASE_URL", "sqlite:///./gold_ledger.db"),
        jwt_secret=jwt_secret,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
    )