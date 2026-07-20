import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.profile_completeness_service import check, stats_access_lock
from tests.factories import make_user


@pytest.mark.asyncio
async def test_check_reports_complete_for_a_fully_filled_profile(session: AsyncSession) -> None:
    user = await make_user(session, "complete@example.com")
    result = check(user)
    assert result.is_complete
    assert result.missing_fields == []


@pytest.mark.asyncio
async def test_check_reports_all_missing_fields_for_a_bare_profile(
    session: AsyncSession,
) -> None:
    user = await make_user(session, "bare@example.com", complete_profile=False)
    result = check(user)
    assert not result.is_complete
    assert set(result.missing_fields) == {
        "birthday",
        "avatar",
        "city",
        "gender",
        "phone",
        "running_club",
        "prior_experience",
    }


@pytest.mark.asyncio
async def test_check_treats_empty_running_club_as_answered(session: AsyncSession) -> None:
    """Empty string is the "not in a club" checkbox — a deliberate answer,
    distinct from never having touched the field at all."""
    user = await make_user(session, "noclub@example.com")
    user.running_club = ""
    result = check(user)
    assert "running_club" not in result.missing_fields


@pytest.mark.asyncio
async def test_check_flags_unverified_email(session: AsyncSession) -> None:
    user = await make_user(session, "unverified@example.com")
    user.email_verified = False
    result = check(user)
    assert "email_verified" in result.missing_fields


def test_stats_access_lock_anonymous() -> None:
    reason, missing = stats_access_lock(None)
    assert reason == "anonymous"
    assert missing == []


@pytest.mark.asyncio
async def test_stats_access_lock_incomplete_profile(session: AsyncSession) -> None:
    user = await make_user(session, "lock-incomplete@example.com", complete_profile=False)
    reason, missing = stats_access_lock(user)
    assert reason == "profile_incomplete"
    assert "birthday" in missing


@pytest.mark.asyncio
async def test_stats_access_lock_unlocked_for_complete_profile(session: AsyncSession) -> None:
    user = await make_user(session, "lock-complete@example.com")
    reason, missing = stats_access_lock(user)
    assert reason is None
    assert missing == []
