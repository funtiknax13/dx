import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.attendance import AttendanceRecord
from app.models.enums import AvatarReview, FinishStatus, UserRole
from tests.factories import make_event_group, make_user


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.mark.asyncio
async def test_pending_avatar_hidden_from_others_visible_to_owner(
    session: AsyncSession, client: AsyncClient
) -> None:
    owner = await make_user(session, "owner-av@e.com")
    owner.avatar = "/media/avatars/owner.jpg"
    owner.avatar_review = AvatarReview.pending
    viewer = await make_user(session, "viewer-av@e.com")
    await session.commit()

    # A stranger sees the placeholder (no avatar) while the photo is pending.
    other = await client.get(f"/api/v1/users/{owner.id}", headers=_auth(viewer.id))
    assert other.status_code == 200, other.text
    assert other.json()["avatar"] is None

    # The owner still sees their own pending photo on their public profile.
    mine = await client.get(f"/api/v1/users/{owner.id}", headers=_auth(owner.id))
    assert mine.json()["avatar"] == "/media/avatars/owner.jpg"

    # Once approved, everyone sees it.
    owner.avatar_review = AvatarReview.approved
    await session.commit()
    after = await client.get(f"/api/v1/users/{owner.id}", headers=_auth(viewer.id))
    assert after.json()["avatar"] == "/media/avatars/owner.jpg"


@pytest.mark.asyncio
async def test_pending_avatar_masked_in_rating(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-av@e.com", UserRole.organizer)
    owner = await make_user(session, "rated-av@e.com")
    owner.avatar = "/media/avatars/rated.jpg"
    owner.avatar_review = AvatarReview.pending
    viewer = await make_user(session, "rater-av@e.com")
    _, group = await make_event_group(session, org)
    session.add(
        AttendanceRecord(
            group_id=group.id,
            raw_name="R",
            runner_id=owner.id,
            finish_status=FinishStatus.finished,
        )
    )
    await session.commit()

    def _avatar_of(body: dict, runner_id: int) -> str | None:
        row = next(e for e in body["entries"] if e["runner_id"] == runner_id)
        return row["avatar"]

    seen_by_other = await client.get("/api/v1/rating", headers=_auth(viewer.id))
    assert _avatar_of(seen_by_other.json(), owner.id) is None

    seen_by_owner = await client.get("/api/v1/rating", headers=_auth(owner.id))
    assert _avatar_of(seen_by_owner.json(), owner.id) == "/media/avatars/rated.jpg"
