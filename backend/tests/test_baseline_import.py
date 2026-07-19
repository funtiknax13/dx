from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runner_baseline import RunnerBaseline
from app.services.baseline_import_service import import_baseline_csv
from tests.factories import make_baseline, make_user


@pytest.mark.asyncio
async def test_import_creates_and_matches_by_email(session: AsyncSession) -> None:
    runner = await make_user(session, "known@example.com")

    csv = (
        "first_name;last_name;dx_count;total_runs;total_km;email\n"
        "Known;Runner;47;50;623.5;known@example.com\n"
        "New;Guest;10;12;80\n"
    )
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 2
    assert result.updated == 0
    assert result.auto_matched == 1
    assert result.guests_created == 1

    known_baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == runner.id)
    )
    assert known_baseline is not None
    assert known_baseline.dx_count == 47
    assert known_baseline.total_runs == 50
    assert known_baseline.total_km == 623.5


@pytest.mark.asyncio
async def test_import_blank_numbers_default_to_zero(session: AsyncSession) -> None:
    csv = "first_name;last_name;dx_count\nBare;Runner;\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.dx_count == 0
    assert baseline.total_runs == 0
    assert baseline.total_km == 0.0


@pytest.mark.asyncio
async def test_import_re_run_overwrites_not_accumulates(session: AsyncSession) -> None:
    csv1 = "first_name;last_name;dx_count\nBob;Runner;10\n"
    csv2 = "first_name;last_name;dx_count\nBob;Runner;25\n"

    first = await import_baseline_csv(session, csv1)
    await session.commit()
    second = await import_baseline_csv(session, csv2)
    await session.commit()

    assert first.created == 1
    assert second.created == 0
    assert second.updated == 1
    assert second.guests_reused == 1

    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.dx_count == 25  # overwritten, not 10 + 25


@pytest.mark.asyncio
async def test_import_skips_empty_name_and_invalid_number(session: AsyncSession) -> None:
    csv = "first_name;last_name;dx_count\n;;\nBad;Number;not-a-number\nGood;Runner;5\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    assert result.skipped_empty == 1
    assert result.skipped_invalid_number == 1


@pytest.mark.asyncio
async def test_import_comma_decimal_km_is_parsed(session: AsyncSession) -> None:
    csv = "first_name;last_name;total_km\nComma;Decimal;623,5\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.total_km == 623.5


@pytest.mark.asyncio
async def test_import_missing_name_columns_raises(session: AsyncSession) -> None:
    with pytest.raises(ValueError):
        await import_baseline_csv(session, "dx_count\n5\n")


@pytest.mark.asyncio
async def test_import_redirects_to_merged_real_account(session: AsyncSession) -> None:
    """A guest with a baseline that's already been claimed/merged should have
    later imports of the same name land straight on the real account."""
    from app.services.guest_service import create_guest, merge_guest_into

    real_user = await make_user(session, "real@example.com")
    guest = await create_guest(session, "Carol Runner")
    await make_baseline(session, guest, dx_count=5)
    await merge_guest_into(session, guest, real_user)
    await session.commit()

    result = await import_baseline_csv(session, "first_name;last_name;dx_count\nCarol;Runner;20\n")
    await session.commit()

    assert result.merged_redirects == 1
    assert result.updated == 1  # real_user already has the merged-in baseline

    baseline = await session.scalar(
        select(RunnerBaseline).where(RunnerBaseline.runner_id == real_user.id)
    )
    assert baseline is not None
    assert baseline.dx_count == 20  # overwritten by the new CSV row


@pytest.mark.asyncio
async def test_import_first_run_date_is_parsed(session: AsyncSession) -> None:
    csv = "first_name;last_name;first_run_date\nDave;Runner;2019-03-01\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.first_run_date == date(2019, 3, 1)


@pytest.mark.asyncio
async def test_import_blank_first_run_date_is_null(session: AsyncSession) -> None:
    csv = "first_name;last_name;first_run_date\nDave;Runner;\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.first_run_date is None


@pytest.mark.asyncio
async def test_import_invalid_first_run_date_is_skipped(session: AsyncSession) -> None:
    csv = "first_name;last_name;first_run_date\nDave;Runner;not-a-date\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 0
    assert result.skipped_invalid_number == 1


@pytest.mark.asyncio
async def test_import_this_year_columns_are_parsed(session: AsyncSession) -> None:
    csv = (
        "first_name;last_name;dx_count;dx_count_this_year;km_this_year;baseline_year\n"
        "Ivan;Petrov;100;26;260,5;2026\n"
    )
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.dx_count == 100
    assert baseline.dx_count_this_year == 26
    assert baseline.km_this_year == 260.5
    assert baseline.baseline_year == 2026


@pytest.mark.asyncio
async def test_import_blank_this_year_columns_default_sensibly(session: AsyncSession) -> None:
    """dx_count_this_year/km_this_year blank -> 0 (same as the other numeric
    columns), but baseline_year blank -> None (no sensible zero for a year)."""
    csv = (
        "first_name;last_name;dx_count_this_year;km_this_year;baseline_year\n"
        "Bare;Runner;;;\n"
    )
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 1
    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.dx_count_this_year == 0
    assert baseline.km_this_year == 0.0
    assert baseline.baseline_year is None


@pytest.mark.asyncio
async def test_import_invalid_baseline_year_is_skipped(session: AsyncSession) -> None:
    csv = "first_name;last_name;baseline_year\nDave;Runner;not-a-year\n"
    result = await import_baseline_csv(session, csv)
    await session.commit()

    assert result.created == 0
    assert result.skipped_invalid_number == 1


@pytest.mark.asyncio
async def test_import_re_run_overwrites_this_year_columns(session: AsyncSession) -> None:
    csv1 = (
        "first_name;last_name;dx_count_this_year;km_this_year;baseline_year\n"
        "Bob;Runner;10;100;2025\n"
    )
    csv2 = (
        "first_name;last_name;dx_count_this_year;km_this_year;baseline_year\n"
        "Bob;Runner;26;260;2026\n"
    )

    await import_baseline_csv(session, csv1)
    await session.commit()
    await import_baseline_csv(session, csv2)
    await session.commit()

    baseline = await session.scalar(select(RunnerBaseline))
    assert baseline is not None
    assert baseline.dx_count_this_year == 26
    assert baseline.km_this_year == 260.0
    assert baseline.baseline_year == 2026
