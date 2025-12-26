from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Request, Response, HTTPException, status
from app.config import settings

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGO = "HS256"
COOKIE_NAME = "qr_attendance_token"

def hash_password(p: str) -> str:
    return pwd.hash(p)

def verify_password(p: str, hashed: str) -> bool:
    return pwd.verify(p, hashed)

def create_token(sub: str) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_expire_min)
    payload = {"sub": sub, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGO)

def set_auth_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.jwt_expire_min * 60,
        path="/",
    )

def clear_auth_cookie(resp: Response) -> None:
    resp.delete_cookie(COOKIE_NAME, path="/")

def get_current_username(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        data = jwt.decode(token, settings.secret_key, algorithms=[ALGO])
        return data.get("sub")
    except JWTError:
        return None

def require_user(request: Request) -> str:
    u = get_current_username(request)
    if not u:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    return u
