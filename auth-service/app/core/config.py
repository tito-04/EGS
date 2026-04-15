from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
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

    # Refresh token cookie
    AUTH_REFRESH_COOKIE_NAME: str = "egs_refresh_token"
    AUTH_REFRESH_COOKIE_DOMAIN: Optional[str] = None
    AUTH_REFRESH_COOKIE_PATH: str = "/"
    AUTH_REFRESH_COOKIE_SAMESITE: str = "lax"
    AUTH_REFRESH_COOKIE_SECURE: bool = False
    AUTH_REFRESH_COOKIE_HTTPONLY: bool = True
    
    # Service
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "info"
    SERVICE_NAME: str = "auth-service"
    API_V1_STR: str = "/api/v1"
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"
    INTERNAL_SERVICE_KEY: str = "change-me-in-production"

    # Password reset email
    SERVICE_PUBLIC_BASE_URL: str = "http://localhost:8000"
    PASSWORD_RESET_LINK_PATH: str = "/reset-password"
    EMAIL_ENABLED: bool = False
    EMAIL_FROM: str = "noreply@egs.local"
    EMAIL_HOST: str = "localhost"
    EMAIL_PORT: int = 1025
    EMAIL_USERNAME: Optional[str] = None
    EMAIL_PASSWORD: Optional[str] = None
    EMAIL_USE_TLS: bool = False
    EMAIL_USE_SSL: bool = False

    # Rate limiting
    RATE_LIMIT_LOGIN: str = "20/minute"
    RATE_LIMIT_FORGOT_PASSWORD: str = "10/minute"
    RATE_LIMIT_RESET_PASSWORD: str = "10/minute"
    RATE_LIMIT_VERIFY: str = "120/minute"
    
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

    @property
    def backend_cors_origins(self) -> list[str]:
        """Return normalized list of allowed redirect origins."""
        values = [item.strip().rstrip("/") for item in self.BACKEND_CORS_ORIGINS.split(",")]
        return [item for item in values if item]

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

        self._validate_https_public_url(self.SERVICE_PUBLIC_BASE_URL, "SERVICE_PUBLIC_BASE_URL")

        if not self.backend_cors_origins:
            raise ValueError("BACKEND_CORS_ORIGINS must not be empty in production")

        for origin in self.backend_cors_origins:
            parsed = urlparse(origin)
            if parsed.scheme != "https" or self._is_local_hostname(parsed.hostname):
                raise ValueError("BACKEND_CORS_ORIGINS must only include HTTPS non-local origins in production")

        samesite = self.AUTH_REFRESH_COOKIE_SAMESITE.strip().lower()
        if samesite not in {"strict", "lax", "none"}:
            raise ValueError("AUTH_REFRESH_COOKIE_SAMESITE must be strict, lax, or none")
        if not self.AUTH_REFRESH_COOKIE_SECURE:
            raise ValueError("AUTH_REFRESH_COOKIE_SECURE must be true in production")
        if samesite == "none":
            raise ValueError("AUTH_REFRESH_COOKIE_SAMESITE=none is not allowed in production")


settings = Settings()
