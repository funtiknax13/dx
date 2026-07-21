import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from tests.factories import make_user


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
