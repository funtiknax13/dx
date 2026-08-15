import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from tests.factories import make_user


@pytest.mark.asyncio
async def test_profile_update_capitalizes_and_rejects_digit_names(
    session: AsyncSession, client: AsyncClient
) -> None:
    user = await make_user(session, "namecheck@example.com")
    await session.commit()
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Lowercase name is capitalised server-side.
    ok = await client.patch(
        "/api/v1/users/me", headers=headers, json={"first_name": "пётр", "last_name": "иванов"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["first_name"] == "Пётр"
    assert ok.json()["last_name"] == "Иванов"

    # A digit in a name (own or guardian) is rejected.
    for field in ("first_name", "last_name", "parent_first_name", "parent_last_name"):
        bad = await client.patch(
            "/api/v1/users/me", headers=headers, json={field: "Иван3"}
        )
        assert bad.status_code == 422, f"{field}: {bad.text}"


@pytest.mark.asyncio
async def test_profile_update_name_charset(session: AsyncSession, client: AsyncClient) -> None:
    """Only Cyrillic letters, space, hyphen and apostrophe — no Latin letters,
    no other symbols/emoji, no leading/trailing/doubled separators."""
    user = await make_user(session, "namecharset@example.com")
    await session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    ok = await client.patch(
        "/api/v1/users/me",
        headers=headers,
        json={"first_name": "анна-мария", "last_name": "о'коннор"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["first_name"] == "Анна-мария"
    assert ok.json()["last_name"] == "О'коннор"

    for value in ("Ivan", "Иван_", "Иван!", "Иван🏃", "-Иван", "Иван--Петров"):
        bad = await client.patch(
            "/api/v1/users/me", headers=headers, json={"first_name": value}
        )
        assert bad.status_code == 422, f"{value!r}: {bad.text}"


@pytest.mark.asyncio
async def test_prior_experience_can_be_set_once(session: AsyncSession, client: AsyncClient) -> None:
    user = await make_user(session, "prior-exp1@example.com", complete_profile=False)
    await session.commit()

    token = create_access_token(user.id)
    resp = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"prior_experience": "never"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["prior_experience"] == "never"


@pytest.mark.asyncio
async def test_prior_experience_is_frozen_after_first_answer(
    session: AsyncSession, client: AsyncClient
) -> None:
    """Regression guard: once answered, switching from "never" to "once"/
    "multiple" must not be possible through self-service — that would let a
    runner dodge the newbie survey requirement (see
    survey_service.stats_locked_pending_survey)."""
    user = await make_user(session, "prior-exp2@example.com", complete_profile=False)
    await session.commit()
    token = create_access_token(user.id)

    first = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"prior_experience": "never"},
    )
    assert first.json()["prior_experience"] == "never"

    second = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"prior_experience": "multiple"},
    )
    assert second.status_code == 200, second.text
    # Silently ignored, not applied — still "never".
    assert second.json()["prior_experience"] == "never"


@pytest.mark.asyncio
async def test_other_fields_still_update_once_prior_experience_is_frozen(
    session: AsyncSession, client: AsyncClient
) -> None:
    """The freeze only applies to prior_experience — it shouldn't silently
    drop the rest of the payload in the same request."""
    user = await make_user(session, "prior-exp3@example.com", complete_profile=False)
    await session.commit()
    token = create_access_token(user.id)

    await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"prior_experience": "never"},
    )
    resp = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"prior_experience": "multiple", "city": "Чебоксары"},
    )
    body = resp.json()
    assert body["prior_experience"] == "never"
    assert body["city"] == "Чебоксары"


@pytest.mark.asyncio
async def test_change_password_enforces_same_charset_as_registration(
    session: AsyncSession, client: AsyncClient
) -> None:
    user = await make_user(session, "pwcharset@example.com")
    await session.commit()
    headers = {"Authorization": f"Bearer {create_access_token(user.id)}"}

    for new_password in ("short1", "onlyletters", "12345678", "пароль1234"):
        bad = await client.post(
            "/api/v1/users/me/password",
            headers=headers,
            json={"current_password": "password123", "new_password": new_password},
        )
        assert bad.status_code == 422, f"{new_password!r}: {bad.text}"

    ok = await client.post(
        "/api/v1/users/me/password",
        headers=headers,
        json={"current_password": "password123", "new_password": "newpass456!"},
    )
    assert ok.status_code == 200, ok.text
