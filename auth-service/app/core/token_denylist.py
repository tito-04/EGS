import hashlib
import time

from app.core.redis_client import get_redis
from app.core.security import verify_token


def _denylist_key(token: str, token_type: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"denylist:{token_type}:{digest}"


async def denylist_token(token: str, token_type: str) -> bool:
    """Store a token in denylist until its expiration."""
    payload = verify_token(token, token_type=token_type)
    if not payload:
        return False

    exp = payload.get("exp")
    if not isinstance(exp, int):
        return False

    ttl_seconds = exp - int(time.time())
    if ttl_seconds <= 0:
        return False

    redis_client = get_redis()
    await redis_client.setex(_denylist_key(token, token_type), ttl_seconds, "1")
    return True


async def is_token_denylisted(token: str, token_type: str) -> bool:
    """Check whether a token is denylisted."""
    redis_client = get_redis()
    return bool(await redis_client.exists(_denylist_key(token, token_type)))


async def denylist_access_token(token: str) -> bool:
    """Store an access token in denylist until its expiration."""
    return await denylist_token(token, token_type="access")


async def denylist_refresh_token(token: str) -> bool:
    """Store a refresh token in denylist until its expiration."""
    return await denylist_token(token, token_type="refresh")


async def is_access_token_denylisted(token: str) -> bool:
    """Check whether an access token is denylisted."""
    return await is_token_denylisted(token, token_type="access")


async def is_refresh_token_denylisted(token: str) -> bool:
    """Check whether a refresh token is denylisted."""
    return await is_token_denylisted(token, token_type="refresh")
