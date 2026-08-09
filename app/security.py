"""Password hashing + JWT issuing/verification."""
import datetime as dt

import bcrypt
import jwt

from .config import config

ALGORITHM = "HS256"
TOKEN_TTL_HOURS = 24 * 7


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_access_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": dt.datetime.utcnow() + dt.timedelta(hours=TOKEN_TTL_HOURS),
        "iat": dt.datetime.utcnow(),
    }
    return jwt.encode(payload, config.effective_jwt_secret, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, config.effective_jwt_secret, algorithms=[ALGORITHM])
