import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import AvatarReview, UserRole
from app.models.support import SupportTicket
from app.models.user import User
from app.services.staff_attention_service import pending_avatar_count
from tests.factories import make_user


async def _login(client: AsyncClient, user_id: int) -> None:
    token = create_access_token(user_id)
    resp = await client.get(f"/admin-tools/sso?token={token}", follow_redirects=False)
    assert resp.status_code == 302


@pytest.mark.asyncio
async def test_pending_avatar_shows_in_queue_and_count(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-av@example.com", UserRole.admin)
    runner = await make_user(session, "runner-av@example.com")
    runner.avatar = "/media/avatars/x.jpg"
    runner.avatar_review = AvatarReview.pending
    await session.commit()

    assert await pending_avatar_count(session) == 1

    await _login(client, admin.id)
    resp = await client.get("/admin-tools/avatars")
    assert resp.status_code == 200
    assert "/media/avatars/x.jpg" in resp.text


@pytest.mark.asyncio
async def test_approve_keeps_avatar(session: AsyncSession, client: AsyncClient) -> None:
    admin = await make_user(session, "admin-av2@example.com", UserRole.admin)
    runner = await make_user(session, "runner-av2@example.com")
    runner.avatar = "/media/avatars/y.jpg"
    runner.avatar_review = AvatarReview.pending
    rid = runner.id
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(f"/admin-tools/avatars/{rid}/approve", follow_redirects=False)
    assert resp.status_code == 303
    session.expire_all()
    u = await session.get(User, rid)
    assert u is not None and u.avatar == "/media/avatars/y.jpg"
    assert u.avatar_review == AvatarReview.approved


@pytest.mark.asyncio
async def test_remove_clears_avatar_and_notifies(
    session: AsyncSession, client: AsyncClient
) -> None:
    admin = await make_user(session, "admin-av3@example.com", UserRole.admin)
    runner = await make_user(session, "runner-av3@example.com")
    runner.avatar = "/media/avatars/z.jpg"
    runner.avatar_review = AvatarReview.pending
    rid = runner.id
    await session.commit()
    await _login(client, admin.id)

    resp = await client.post(f"/admin-tools/avatars/{rid}/remove", follow_redirects=False)
    assert resp.status_code == 303
    session.expire_all()
    u = await session.get(User, rid)
    assert u is not None and u.avatar is None
    assert u.avatar_review == AvatarReview.approved

    ticket = await session.scalar(
        select(SupportTicket).where(SupportTicket.created_by_user_id == rid)
    )
    assert ticket is not None  # runner was notified via a closed ticket


@pytest.mark.asyncio
async def test_avatars_page_forbidden_for_non_admin(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-av@example.com", UserRole.organizer)
    await session.commit()
    await _login(client, org.id)
    resp = await client.get("/admin-tools/avatars", follow_redirects=False)
    assert resp.status_code == 303  # redirected away from the admin-only page
