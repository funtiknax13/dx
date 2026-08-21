import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import ModerationStatus, UserRole
from app.models.profile_edit_request import ProfileEditRequest
from app.models.support import SupportMessage, SupportTicket
from app.models.user import User
from app.services.profile_completeness_service import stats_access_lock
from app.services.profile_review_service import (
    PLACEHOLDER_FIRST_NAME,
    PLACEHOLDER_LAST_NAME,
    approve,
    has_pending_review,
    is_awaiting_first_review,
    pending_request_for,
    reject,
    submit_for_review,
)
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_submit_only_stages_actually_changed_fields(session: AsyncSession) -> None:
    user = await make_user(session, "diff@example.com")
    await session.commit()

    request = await submit_for_review(
        session, user, {"first_name": user.first_name, "city": "Казань"}
    )
    await session.commit()

    assert request is not None
    assert request.changes == {"city": "Казань"}  # first_name unchanged, dropped
    assert user.city != "Казань"  # not applied yet


@pytest.mark.asyncio
async def test_resubmitting_replaces_the_pending_request(session: AsyncSession) -> None:
    user = await make_user(session, "resubmit@example.com")
    await session.commit()

    first = await submit_for_review(session, user, {"city": "Казань"})
    await session.commit()
    assert first is not None

    second = await submit_for_review(session, user, {"city": "Уфа"})
    await session.commit()
    assert second is not None
    assert second.changes == {"city": "Уфа"}

    # Exactly one pending request for this user, and it's the new one — not
    # left dangling alongside the first (note: SQLite reuses a deleted row's
    # id for the next insert, so asserting on `first.id` disappearing isn't a
    # reliable signal here; the content and the count are).
    pending = list(
        await session.scalars(
            select(ProfileEditRequest).where(ProfileEditRequest.user_id == user.id)
        )
    )
    assert len(pending) == 1
    assert pending[0].changes == {"city": "Уфа"}


@pytest.mark.asyncio
async def test_resubmitting_the_committed_value_cancels_the_pending_request(
    session: AsyncSession,
) -> None:
    """Reverting a staged edit back to what's already live leaves nothing to
    review — the pending request is dropped outright, not kept as a no-op."""
    user = await make_user(session, "revert@example.com")
    original_city = user.city
    await session.commit()

    await submit_for_review(session, user, {"city": "Казань"})
    await session.commit()
    assert await has_pending_review(session, user)

    result = await submit_for_review(session, user, {"city": original_city})
    await session.commit()

    assert result is None
    assert not await has_pending_review(session, user)


@pytest.mark.asyncio
async def test_approve_applies_changes_and_mirrors_city_name(session: AsyncSession) -> None:
    from app.models.city import City

    session.add(
        City(
            id=77,
            name="Казань",
            name_ascii="Kazan",
            search_name="казань",
            search_ascii="kazan",
            country_code="RU",
            lat=55.8,
            lng=49.1,
            population=1_200_000,
        )
    )
    user = await make_user(session, "approve@example.com")
    await session.commit()

    request = await submit_for_review(session, user, {"city_id": 77, "gender": "female"})
    await session.commit()
    assert request is not None

    await approve(session, request)
    await session.commit()
    await session.refresh(user)

    assert user.city_id == 77
    assert user.city == "Казань"  # mirrored, not just city_id applied
    assert user.gender == "female"
    assert request.status == ModerationStatus.approved
    assert request.decided_at is not None


@pytest.mark.asyncio
async def test_reject_leaves_user_untouched_and_notifies(session: AsyncSession) -> None:
    admin = await make_user(session, "admin-reject@example.com", UserRole.admin)
    user = await make_user(session, "reject-me@example.com")
    original_city = user.city
    await session.commit()

    request = await submit_for_review(session, user, {"city": "Казань"})
    await session.commit()
    assert request is not None

    await reject(session, request, admin, "Похоже на опечатку")
    await session.commit()
    await session.refresh(user)

    assert user.city == original_city  # untouched
    assert request.status == ModerationStatus.rejected

    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == user.id)
    )
    assert ticket is not None
    msg = await session.scalar(select(SupportMessage).where(SupportMessage.ticket_id == ticket.id))
    assert msg is not None and "Похоже на опечатку" in msg.body


@pytest.mark.asyncio
async def test_registration_bootstrap_and_needs_reentry_after_rejection(
    client: AsyncClient, session: AsyncSession
) -> None:
    """A fresh registration gets the placeholder name (see
    is_awaiting_first_review); rejecting its first submission leaves the
    placeholder in place, which the frontend reads as "enter real data"."""
    admin = await make_user(session, "admin-boot@example.com", UserRole.admin)
    await session.commit()

    payload = {
        "first_name": "Анна",
        "last_name": "Смирнова",
        "email": "bootstrap@example.com",
        "password": "supersecret1",
        "accept_privacy_policy": True,
    }
    r = await client.post("/api/v1/auth/register", json=payload)
    assert r.status_code == 201, r.text

    user = await session.scalar(select(User).where(User.email == payload["email"]))
    assert user is not None
    assert user.first_name == PLACEHOLDER_FIRST_NAME
    assert user.last_name == PLACEHOLDER_LAST_NAME
    assert is_awaiting_first_review(user)

    request = await pending_request_for(session, user)
    assert request is not None

    await reject(session, request, admin, "Похоже на набор букв")
    await session.commit()
    await session.refresh(user)

    # Still the placeholder — rejection doesn't invent a fallback name.
    assert is_awaiting_first_review(user)


@pytest.mark.asyncio
async def test_stats_access_lock_reports_pending_review(session: AsyncSession) -> None:
    user = await make_user(session, "gated@example.com")
    await session.commit()
    reason, missing = await stats_access_lock(session, user)
    assert reason is None  # complete profile, nothing pending yet

    await submit_for_review(session, user, {"city": "Казань"})
    await session.commit()

    reason, missing = await stats_access_lock(session, user)
    assert reason == "profile_pending_review"
    assert missing == []


@pytest.mark.asyncio
async def test_profile_update_api_stages_instead_of_applying(
    session: AsyncSession, client: AsyncClient
) -> None:
    user = await make_user(session, "api-stage@example.com")
    await session.commit()
    token = create_access_token(user.id)

    resp = await client.patch(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
        json={"city": "Казань"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["city"] != "Казань"
    assert body["pending_review"]["changes"]["city"] == "Казань"


@pytest.mark.asyncio
async def test_admin_queue_approve_and_reject_routes(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-queue@example.com", UserRole.admin)
    approve_target = await make_user(session, "queue-approve@example.com")
    reject_target = await make_user(session, "queue-reject@example.com")
    await session.commit()

    approve_request = await submit_for_review(session, approve_target, {"city": "Казань"})
    reject_request = await submit_for_review(session, reject_target, {"city": "Уфа"})
    await session.commit()
    assert approve_request is not None and reject_request is not None

    await _login(client, admin.id)

    listing = await client.get("/admin-tools/profile-review")
    assert listing.status_code == 200
    assert "Казань" in listing.text and "Уфа" in listing.text

    r1 = await client.post(
        f"/admin-tools/profile-review/{approve_request.id}/approve", follow_redirects=False
    )
    assert r1.status_code == 303
    r2 = await client.post(
        f"/admin-tools/profile-review/{reject_request.id}/reject",
        data={"reason": "Недостоверно"},
        follow_redirects=False,
    )
    assert r2.status_code == 303

    session.expire_all()
    await session.refresh(approve_target)
    await session.refresh(reject_target)
    assert approve_target.city == "Казань"
    assert reject_target.city != "Уфа"

    empty = await client.get("/admin-tools/profile-review")
    assert "Нет анкет на проверке" in empty.text


@pytest.mark.asyncio
async def test_profile_review_page_forbidden_for_non_admin(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-review@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)
    resp = await client.get("/admin-tools/profile-review", follow_redirects=False)
    assert resp.status_code == 302  # bounced to login, same as CSV import/baselines for organizer
