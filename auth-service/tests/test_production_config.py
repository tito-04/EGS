from app.core.config import Settings


def test_development_allows_local_defaults() -> None:
    settings = Settings(_env_file=None, ENVIRONMENT="development")
    settings.validate_security_configuration()


def test_production_rejects_placeholder_secret_key() -> None:
    settings = Settings(_env_file=None, ENVIRONMENT="production")

    try:
        settings.validate_security_configuration()
        assert False, "Expected production validation to fail for placeholder SECRET_KEY"
    except ValueError as exc:
        assert "SECRET_KEY" in str(exc)


def test_production_rejects_insecure_cookie() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="A" * 64,
        INTERNAL_SERVICE_KEY="B" * 32,
        SSO_COOKIE_SECURE=False,
        SERVICE_PUBLIC_BASE_URL="https://auth.example.com",
        ALLOWED_REDIRECT_ORIGINS="https://flashsale.example.com",
        AUTH_CLIENTS_JSON='{"flash-sale": ["https://flashsale.example.com/callback"]}',
    )

    try:
        settings.validate_security_configuration()
        assert False, "Expected production validation to fail for insecure cookie"
    except ValueError as exc:
        assert "SSO_COOKIE_SECURE" in str(exc)


def test_production_rejects_non_https_redirect_origin() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="A" * 64,
        INTERNAL_SERVICE_KEY="B" * 32,
        SSO_COOKIE_SECURE=True,
        SERVICE_PUBLIC_BASE_URL="https://auth.example.com",
        ALLOWED_REDIRECT_ORIGINS="http://flashsale.example.com",
        AUTH_CLIENTS_JSON='{"flash-sale": ["https://flashsale.example.com/callback"]}',
    )

    try:
        settings.validate_security_configuration()
        assert False, "Expected production validation to fail for non-HTTPS redirect origin"
    except ValueError as exc:
        assert "ALLOWED_REDIRECT_ORIGINS" in str(exc)


def test_production_valid_configuration_passes() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="A" * 64,
        INTERNAL_SERVICE_KEY="B" * 32,
        SSO_COOKIE_SECURE=True,
        SERVICE_PUBLIC_BASE_URL="https://auth.example.com",
        ALLOWED_REDIRECT_ORIGINS="https://flashsale.example.com,https://payment.example.com",
        AUTH_CLIENTS_JSON='{"flash-sale": ["https://flashsale.example.com/callback"], "payment": ["https://payment.example.com/callback"]}',
    )

    settings.validate_security_configuration()
