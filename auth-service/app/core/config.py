from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
import json
from urllib.parse import urlparse


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/auth_db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # JWT
    SECRET_KEY: str = "your-super-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 15
    AUTH_CODE_EXPIRE_SECONDS: int = 60
    
    # Service
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "info"
    SERVICE_NAME: str = "auth-service"
    API_V1_STR: str = "/api/v1"
    ALLOWED_REDIRECT_ORIGINS: str = "http://localhost:3000"
    SSO_COOKIE_NAME: str = "egs_sso"
    SSO_COOKIE_DOMAIN: Optional[str] = None
    SSO_COOKIE_SECURE: bool = False
    SSO_COOKIE_SAMESITE: str = "lax"
    AUTH_CLIENTS_JSON: str = '{"flash-sale": ["http://localhost:3000/callback"], "payment": ["http://localhost:3001/callback"]}'
    INTERNAL_SERVICE_KEY: str = "change-me-in-production"

    # Password reset email
    SERVICE_PUBLIC_BASE_URL: str = "http://localhost:8000"
    PASSWORD_RESET_LINK_PATH: str = "/ui/reset-password"
    EMAIL_ENABLED: bool = False
    EMAIL_FROM: str = "noreply@egs.local"
    EMAIL_HOST: str = "localhost"
    EMAIL_PORT: int = 1025
    EMAIL_USERNAME: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_USE_TLS: bool = False
    EMAIL_USE_SSL: bool = False
    DEV_EMAIL_TEST_ENABLED: bool = False

    # Rate limiting
    RATE_LIMIT_LOGIN: str = "20/minute"
    RATE_LIMIT_FORGOT_PASSWORD: str = "10/minute"
    RATE_LIMIT_RESET_PASSWORD: str = "10/minute"
    RATE_LIMIT_EXCHANGE_CODE: str = "40/minute"
    RATE_LIMIT_VERIFY: str = "120/minute"
    RATE_LIMIT_UI_LOGIN: str = "20/minute"
    RATE_LIMIT_UI_REGISTER: str = "10/minute"
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    @property
    def allowed_redirect_origins(self) -> list[str]:
        """Return normalized list of allowed redirect origins."""
        values = [item.strip().rstrip("/") for item in self.ALLOWED_REDIRECT_ORIGINS.split(",")]
        return [item for item in values if item]

    @property
    def auth_clients(self) -> dict[str, list[str]]:
        """Return configured clients and allowed redirect URIs per client."""
        try:
            data = json.loads(self.AUTH_CLIENTS_JSON)
            if not isinstance(data, dict):
                return {}

            result: dict[str, list[str]] = {}
            for key, values in data.items():
                if not isinstance(key, str) or not isinstance(values, list):
                    continue
                normalized = []
                for value in values:
                    if isinstance(value, str) and value.strip():
                        normalized.append(value.strip())
                if normalized:
                    result[key] = normalized
            return result
        except json.JSONDecodeError:
            return {}

    @property
    def is_production(self) -> bool:
        """Return true when running in production mode."""
        return self.ENVIRONMENT.lower() == "production"

    @staticmethod
    def _is_local_hostname(hostname: str | None) -> bool:
        if not hostname:
            return True
        lowered = hostname.lower()
        return lowered in {"localhost", "127.0.0.1", "::1"}

    def _validate_https_public_url(self, value: str, field_name: str) -> None:
        parsed = urlparse(value)
        if parsed.scheme != "https" or self._is_local_hostname(parsed.hostname):
            raise ValueError(f"{field_name} must be an HTTPS non-local URL in production")

    def validate_security_configuration(self) -> None:
        """Fail fast when insecure defaults are used in production."""
        if not self.is_production:
            return

        placeholder_values = {
            "your-super-secret-key-change-in-production",
            "change-me-in-production",
            "",
        }

        if self.SECRET_KEY in placeholder_values or len(self.SECRET_KEY) < 32:
            raise ValueError("SECRET_KEY must be replaced with a strong production secret")

        if self.INTERNAL_SERVICE_KEY in placeholder_values or len(self.INTERNAL_SERVICE_KEY) < 24:
            raise ValueError("INTERNAL_SERVICE_KEY must be replaced with a strong production secret")

        if not self.SSO_COOKIE_SECURE:
            raise ValueError("SSO_COOKIE_SECURE must be True in production")

        self._validate_https_public_url(self.SERVICE_PUBLIC_BASE_URL, "SERVICE_PUBLIC_BASE_URL")

        if not self.allowed_redirect_origins:
            raise ValueError("ALLOWED_REDIRECT_ORIGINS must not be empty in production")

        for origin in self.allowed_redirect_origins:
            parsed = urlparse(origin)
            if parsed.scheme != "https" or self._is_local_hostname(parsed.hostname):
                raise ValueError("ALLOWED_REDIRECT_ORIGINS must only include HTTPS non-local origins in production")

        if not self.auth_clients:
            raise ValueError("AUTH_CLIENTS_JSON must contain at least one client in production")

        for client_id, redirect_uris in self.auth_clients.items():
            if not client_id.strip():
                raise ValueError("AUTH_CLIENTS_JSON contains an empty client_id")
            for redirect_uri in redirect_uris:
                parsed = urlparse(redirect_uri)
                if parsed.scheme != "https" or self._is_local_hostname(parsed.hostname):
                    raise ValueError("AUTH_CLIENTS_JSON must only include HTTPS non-local redirect URIs in production")


settings = Settings()
