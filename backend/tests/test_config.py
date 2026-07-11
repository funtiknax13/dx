import pytest

from app.core.config import Settings, _assert_production_is_configured


def _prod_settings(**overrides: str) -> Settings:
    base: dict[str, str] = {
        "environment": "production",
        "secret_key": "a" * 40,
        "admin_secret_key": "b" * 40,
        "initial_admin_password": "a-real-password-not-the-default",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_production_with_real_secrets_passes() -> None:
    _assert_production_is_configured(_prod_settings())


def test_development_skips_the_check_even_with_defaults() -> None:
    _assert_production_is_configured(Settings(environment="development"))


@pytest.mark.parametrize(
    "field", ["secret_key", "admin_secret_key", "initial_admin_password"]
)
def test_production_rejects_leftover_default(field: str) -> None:
    defaults = {
        "secret_key": "change-me",
        "admin_secret_key": "change-me-too",
        "initial_admin_password": "change-me-admin-password",
    }
    with pytest.raises(RuntimeError, match=field):
        _assert_production_is_configured(_prod_settings(**{field: defaults[field]}))


@pytest.mark.parametrize("field", ["secret_key", "admin_secret_key"])
def test_production_rejects_short_secret(field: str) -> None:
    with pytest.raises(RuntimeError, match=field):
        _assert_production_is_configured(_prod_settings(**{field: "too-short"}))
