import os
from dotenv import load_dotenv

load_dotenv()

_INSECURE_JWT_SECRET = "insecure-dev-secret-change-me"


def _normalize_db_url(url: str) -> str:
    """Hosted Postgres providers (Render, Railway, Heroku, Neon, ...) hand out
    `postgres://` / `postgresql://` URLs; SQLAlchemy needs the psycopg 3
    driver named explicitly."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


class Settings:
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    DATABASE_URL: str = _normalize_db_url(os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://bevobiz:bevobiz_dev_pw@localhost:5432/bevobiz",
    ))
    JWT_SECRET: str = os.getenv("JWT_SECRET", _INSECURE_JWT_SECRET)
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))
    # Comma-separated, e.g. "https://bevobiz.vercel.app,http://localhost:5173"
    FRONTEND_ORIGINS: list[str] = [
        o.strip().rstrip("/")
        for o in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")
        if o.strip()
    ]

    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # Connects as a dedicated low-privilege role (SELECT-only on
    # products/sales/businesses, no access to users) — see
    # db/init/002_nlq_readonly_role.sql and app/nlq/db.py. The NLQ safe
    # executor uses this instead of DATABASE_URL; nothing else does.
    NLQ_DATABASE_URL: str = _normalize_db_url(os.getenv(
        "NLQ_DATABASE_URL",
        "postgresql+psycopg://bevobiz_nlq_reader:bevobiz_nlq_reader_dev_pw@localhost:5432/bevobiz",
    ))


settings = Settings()

if settings.ENVIRONMENT == "production" and settings.JWT_SECRET == _INSECURE_JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be set when ENVIRONMENT=production")
