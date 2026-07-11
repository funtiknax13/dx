import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, _assert_production_is_configured
from app.core.security import create_access_token
from app.models.enums import UserRole
from tests.factories import make_user


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


@pytest.mark.asyncio
async def test_admin_tools_session_cookie_not_secure_by_default(
    session: AsyncSession, client: AsyncClient
) -> None:
    """secure_cookies defaults to False, so the admin-tools session cookie must
    not carry the Secure flag — a Secure cookie is silently dropped by
    browsers over plain HTTP, which locks everyone out of /admin-tools and
    SQLAdmin even with a correct password (see conversation: the fix for
    exactly this after the site went live without TLS)."""
    admin = await make_user(session, "cookie-admin@example.com", UserRole.admin)
    await session.commit()
    token = create_access_token(admin.id)

    resp = await client.get(
        f"/admin-tools/sso?token={token}", follow_redirects=False
    )
    assert resp.status_code == 302
    set_cookie = resp.headers.get("set-cookie", "")
    assert "session=" in set_cookie
    assert "secure" not in set_cookie.lower()
