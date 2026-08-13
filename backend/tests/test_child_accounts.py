from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.profile_completeness_service import PARENT_FIELDS, age_years, check
from tests.factories import make_user


def test_age_years_counts_whole_years() -> None:
    assert age_years(date(2000, 1, 1), date(2020, 1, 1)) == 20
    assert age_years(date(2000, 6, 15), date(2020, 6, 14)) == 19  # birthday not reached yet


@pytest.mark.asyncio
async def test_under_14_requires_guardian_fields(session: AsyncSession) -> None:
    user = await make_user(session, "kid@example.com")  # complete adult profile by default
    user.birthday = date(date.today().year - 10, 1, 1)  # 10 years old

    result = check(user)
    assert not result.is_complete
    assert set(PARENT_FIELDS) <= set(result.missing_fields)

    user.parent_first_name = "Мария"
    user.parent_last_name = "Иванова"
    user.parent_phone = "+79990000000"
    assert check(user).is_complete


@pytest.mark.asyncio
async def test_adult_does_not_need_guardian_fields(session: AsyncSession) -> None:
    user = await make_user(session, "adult@example.com")
    user.birthday = date(1990, 1, 1)
    assert check(user).is_complete
    assert not any(f in check(user).missing_fields for f in PARENT_FIELDS)
