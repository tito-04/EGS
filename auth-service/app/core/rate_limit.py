from slowapi import Limiter
from slowapi.util import get_remote_address


def _rate_limit_key(request) -> str:
	"""Prefer forwarded client IP when available, fallback to direct peer."""
	forwarded = request.headers.get("x-forwarded-for")
	if forwarded:
		first_ip = forwarded.split(",", 1)[0].strip()
		if first_ip:
			return first_ip
	return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)
