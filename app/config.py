from pydantic import BaseModel
import os

def _get(name: str, default: str | None = None) -> str:
    v = os.getenv(name, default)
    if v is None:
        raise RuntimeError(f"Missing env var: {name}")
    return v

class Settings(BaseModel):
    database_url: str = _get("DATABASE_URL")
    secret_key: str = _get("SECRET_KEY", "CHANGE_ME")
    app_base_url: str = _get("APP_BASE_URL", "http://127.0.0.1:8000")

    jwt_expire_min: int = int(os.getenv("JWT_EXPIRE_MIN", "10080"))  # 7d
    dynamic_key_ttl_sec: int = int(os.getenv("DYNAMIC_KEY_TTL_SEC", "20"))
    late_after_min: int = int(os.getenv("LATE_AFTER_MIN", "10"))

    cookie_secure: bool = os.getenv("COOKIE_SECURE", "0") == "1"
    cookie_samesite: str = os.getenv("COOKIE_SAMESITE", "lax")

    migrate_on_start: bool = os.getenv("MIGRATE_ON_START", "0") == "1"
    tz: str = os.getenv("TZ", "Europe/Istanbul")

settings = Settings()
