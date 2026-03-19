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


def test_production_rejects_non_https_public_url() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="A" * 64,
        INTERNAL_SERVICE_KEY="B" * 32,
        SERVICE_PUBLIC_BASE_URL="http://auth.example.com",
        BACKEND_CORS_ORIGINS="https://flashsale.example.com",
    )

    try:
        settings.validate_security_configuration()
        assert False, "Expected production validation to fail for non-HTTPS public URL"
    except ValueError as exc:
        assert "SERVICE_PUBLIC_BASE_URL" in str(exc)


def test_production_rejects_non_https_redirect_origin() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="A" * 64,
        INTERNAL_SERVICE_KEY="B" * 32,
        SERVICE_PUBLIC_BASE_URL="https://auth.example.com",
        BACKEND_CORS_ORIGINS="http://flashsale.example.com",
    )

    try:
        settings.validate_security_configuration()
        assert False, "Expected production validation to fail for non-HTTPS redirect origin"
    except ValueError as exc:
        assert "BACKEND_CORS_ORIGINS" in str(exc)


def test_production_valid_configuration_passes() -> None:
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="A" * 64,
        INTERNAL_SERVICE_KEY="B" * 32,
        SERVICE_PUBLIC_BASE_URL="https://auth.example.com",
        BACKEND_CORS_ORIGINS="https://flashsale.example.com,https://payment.example.com",
    )

    settings.validate_security_configuration()
