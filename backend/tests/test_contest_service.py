from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contest import ContestEntry, ContestVote
from app.models.enums import ContestFieldType, ModerationStatus
from app.services.contest_service import (
    ContestValidationError,
    can_submit,
    can_vote,
    cast_vote,
    contest_phase,
    get_entries,
    parse_json_list,
    publish_results,
    set_placement,
    submit_entry,
    vote_tally,
)
from tests.factories import add_contest_field, make_contest, make_user

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
PAST = NOW - timedelta(days=10)
SOON = NOW + timedelta(days=1)
LATER = NOW + timedelta(days=5)
MUCH_LATER = NOW + timedelta(days=10)


# --- contest_phase -----------------------------------------------------


@pytest.mark.asyncio
async def test_phase_draft_when_unpublished(session: AsyncSession) -> None:
    org = await make_user(session, "org-phase1@example.com")
    contest = await make_contest(session, org, is_published=False)
    assert contest_phase(contest, NOW) == "draft"


@pytest.mark.asyncio
async def test_phase_upcoming_when_published_before_submissions_open(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-phase2@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=SOON)
    assert contest_phase(contest, NOW) == "upcoming"


@pytest.mark.asyncio
async def test_phase_upcoming_forever_without_a_submissions_open_date(
    session: AsyncSession,
) -> None:
    """Published but the admin hasn't scheduled a submission window yet —
    stays a teaser indefinitely rather than erroring or guessing."""
    org = await make_user(session, "org-phase3@example.com")
    contest = await make_contest(session, org, is_published=True)
    assert contest_phase(contest, NOW) == "upcoming"


@pytest.mark.asyncio
async def test_phase_submissions_open(session: AsyncSession) -> None:
    org = await make_user(session, "org-phase4@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
    )
    assert contest_phase(contest, NOW) == "submissions_open"


@pytest.mark.asyncio
async def test_phase_submissions_open_indefinitely_without_a_close_date(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-phase5@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=PAST)
    assert contest_phase(contest, NOW) == "submissions_open"


@pytest.mark.asyncio
async def test_phase_submissions_closed_before_voting_opens(session: AsyncSession) -> None:
    org = await make_user(session, "org-phase6@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=SOON,
    )
    assert contest_phase(contest, NOW) == "submissions_closed"


@pytest.mark.asyncio
async def test_phase_voting_open(session: AsyncSession) -> None:
    org = await make_user(session, "org-phase7@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=PAST + timedelta(days=2),
        voting_close_at=SOON,
    )
    assert contest_phase(contest, NOW) == "voting_open"


@pytest.mark.asyncio
async def test_phase_voting_closed_after_voting_close_at(session: AsyncSession) -> None:
    org = await make_user(session, "org-phase8@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=PAST + timedelta(days=2),
        voting_close_at=PAST + timedelta(days=3),
    )
    assert contest_phase(contest, NOW) == "voting_closed"


@pytest.mark.asyncio
async def test_can_submit_and_can_vote_follow_the_phase(session: AsyncSession) -> None:
    org = await make_user(session, "org-phase9@example.com")
    open_contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
    )
    assert can_submit(open_contest, NOW) is True
    assert can_vote(open_contest, NOW) is False

    voting_contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=PAST + timedelta(days=2),
        voting_close_at=SOON,
    )
    assert can_submit(voting_contest, NOW) is False
    assert can_vote(voting_contest, NOW) is True


# --- submit_entry -----------------------------------------------------


async def _open_contest_with_fields(session: AsyncSession, org):
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    link_field = await add_contest_field(
        session, contest, position=0, label="Ссылка", field_type=ContestFieldType.url
    )
    dist_field = await add_contest_field(
        session,
        contest,
        position=1,
        label="Дистанция, км",
        field_type=ContestFieldType.number,
        required=False,
    )
    return contest, link_field, dist_field


@pytest.mark.asyncio
async def test_submit_entry_creates_a_pending_entry(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit1@example.com")
    runner = await make_user(session, "runner-submit1@example.com")
    contest, link_field, dist_field = await _open_contest_with_fields(session, org)

    entry = await submit_entry(
        session,
        contest,
        runner,
        {link_field.id: "https://example.com/route", dist_field.id: "21.5"},
        now=NOW,
    )
    await session.commit()

    assert entry.status == ModerationStatus.pending
    assert entry.runner_id == runner.id
    values = {v.field_id: v.value for v in entry.values}
    assert values[link_field.id] == "https://example.com/route"
    assert values[dist_field.id] == "21.5"


@pytest.mark.asyncio
async def test_submit_entry_rejects_missing_required_field(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit2@example.com")
    runner = await make_user(session, "runner-submit2@example.com")
    contest, link_field, dist_field = await _open_contest_with_fields(session, org)

    with pytest.raises(ContestValidationError) as exc_info:
        await submit_entry(session, contest, runner, {link_field.id: ""}, now=NOW)
    assert link_field.id in exc_info.value.errors


@pytest.mark.asyncio
async def test_submit_entry_rejects_bad_number(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit3@example.com")
    runner = await make_user(session, "runner-submit3@example.com")
    contest, link_field, dist_field = await _open_contest_with_fields(session, org)

    with pytest.raises(ContestValidationError) as exc_info:
        await submit_entry(
            session,
            contest,
            runner,
            {link_field.id: "https://example.com/route", dist_field.id: "не число"},
            now=NOW,
        )
    assert dist_field.id in exc_info.value.errors


@pytest.mark.asyncio
async def test_submit_entry_rejects_bad_url(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit4@example.com")
    runner = await make_user(session, "runner-submit4@example.com")
    contest, link_field, dist_field = await _open_contest_with_fields(session, org)

    with pytest.raises(ContestValidationError) as exc_info:
        await submit_entry(session, contest, runner, {link_field.id: "not-a-url"}, now=NOW)
    assert link_field.id in exc_info.value.errors


@pytest.mark.asyncio
async def test_submit_entry_blocked_outside_submission_window(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit5@example.com")
    runner = await make_user(session, "runner-submit5@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)

    with pytest.raises(ValueError, match="заверш"):
        await submit_entry(session, contest, runner, {field.id: "https://example.com"}, now=NOW)


@pytest.mark.asyncio
async def test_resubmit_after_rejection_clears_status_and_reason(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit6@example.com")
    runner = await make_user(session, "runner-submit6@example.com")
    contest, link_field, dist_field = await _open_contest_with_fields(session, org)

    entry = await submit_entry(
        session, contest, runner, {link_field.id: "https://example.com/a"}, now=NOW
    )
    entry.status = ModerationStatus.rejected
    entry.rejection_reason = "Нет описания маршрута"
    await session.flush()

    updated = await submit_entry(
        session,
        contest,
        runner,
        {link_field.id: "https://example.com/b"},
        entry_id=entry.id,
        now=NOW,
    )
    await session.commit()

    assert updated.id == entry.id  # same row, not a second entry
    assert updated.status == ModerationStatus.pending
    assert updated.rejection_reason is None
    values = {v.field_id: v.value for v in updated.values}
    assert values[link_field.id] == "https://example.com/b"


@pytest.mark.asyncio
async def test_submit_entry_blocked_once_approved(session: AsyncSession) -> None:
    org = await make_user(session, "org-submit7@example.com")
    runner = await make_user(session, "runner-submit7@example.com")
    contest, link_field, dist_field = await _open_contest_with_fields(session, org)

    entry = await submit_entry(
        session, contest, runner, {link_field.id: "https://example.com/a"}, now=NOW
    )
    entry.status = ModerationStatus.approved
    await session.flush()

    with pytest.raises(ValueError, match="подтвержд"):
        await submit_entry(
            session,
            contest,
            runner,
            {link_field.id: "https://example.com/b"},
            entry_id=entry.id,
            now=NOW,
        )


# --- multi_select -----------------------------------------------------


@pytest.mark.asyncio
async def test_multi_select_requires_at_least_one_option_when_required(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-ms1@example.com")
    runner = await make_user(session, "runner-ms1@example.com")
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session,
        contest,
        field_type=ContestFieldType.multi_select,
        options=["Зима", "Весна", "Лето", "Осень"],
    )

    with pytest.raises(ContestValidationError) as exc_info:
        await submit_entry(session, contest, runner, {field.id: "[]"}, now=NOW)
    assert field.id in exc_info.value.errors


@pytest.mark.asyncio
async def test_multi_select_rejects_option_not_in_list(session: AsyncSession) -> None:
    org = await make_user(session, "org-ms2@example.com")
    runner = await make_user(session, "runner-ms2@example.com")
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session, contest, field_type=ContestFieldType.multi_select, options=["Зима", "Лето"]
    )

    with pytest.raises(ContestValidationError) as exc_info:
        await submit_entry(session, contest, runner, {field.id: '["Зима", "Невидимка"]'}, now=NOW)
    assert field.id in exc_info.value.errors


@pytest.mark.asyncio
async def test_multi_select_accepts_valid_selection(session: AsyncSession) -> None:
    org = await make_user(session, "org-ms3@example.com")
    runner = await make_user(session, "runner-ms3@example.com")
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session,
        contest,
        field_type=ContestFieldType.multi_select,
        options=["Зима", "Весна", "Лето", "Осень"],
    )

    entry = await submit_entry(session, contest, runner, {field.id: '["Зима", "Лето"]'}, now=NOW)
    await session.commit()
    values = {v.field_id: v.value for v in entry.values}
    assert parse_json_list(values[field.id]) == ["Зима", "Лето"]


def test_parse_json_list_handles_legacy_bare_string() -> None:
    """Before multi-select/multi-image existed, an image field's value was
    a bare media path — must still read back as a one-item list."""
    assert parse_json_list(None) == []
    assert parse_json_list("") == []
    assert parse_json_list('["a", "b"]') == ["a", "b"]
    assert parse_json_list("/media/contests/1/old.jpg") == ["/media/contests/1/old.jpg"]


# --- multiple entries per runner ---------------------------------------


@pytest.mark.asyncio
async def test_second_entry_creates_a_new_row_when_unlimited(session: AsyncSession) -> None:
    org = await make_user(session, "org-multi1@example.com")
    runner = await make_user(session, "runner-multi1@example.com")
    contest, link_field, _dist_field = await _open_contest_with_fields(session, org)

    first = await submit_entry(
        session, contest, runner, {link_field.id: "https://example.com/a"}, now=NOW
    )
    second = await submit_entry(
        session, contest, runner, {link_field.id: "https://example.com/b"}, now=NOW
    )
    await session.commit()

    assert first.id != second.id
    entries = await get_entries(session, contest.id, runner.id)
    assert {e.id for e in entries} == {first.id, second.id}


@pytest.mark.asyncio
async def test_second_entry_blocked_once_cap_reached(session: AsyncSession) -> None:
    org = await make_user(session, "org-multi2@example.com")
    runner = await make_user(session, "runner-multi2@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
        max_entries_per_runner=1,
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)

    await submit_entry(session, contest, runner, {field.id: "https://example.com/a"}, now=NOW)

    with pytest.raises(ValueError, match="не более 1"):
        await submit_entry(session, contest, runner, {field.id: "https://example.com/b"}, now=NOW)


@pytest.mark.asyncio
async def test_editing_existing_entry_does_not_count_against_the_cap(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-multi3@example.com")
    runner = await make_user(session, "runner-multi3@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
        max_entries_per_runner=1,
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)

    entry = await submit_entry(
        session, contest, runner, {field.id: "https://example.com/a"}, now=NOW
    )
    updated = await submit_entry(
        session, contest, runner, {field.id: "https://example.com/b"}, entry_id=entry.id, now=NOW
    )
    await session.commit()

    assert updated.id == entry.id
    entries = await get_entries(session, contest.id, runner.id)
    assert len(entries) == 1


@pytest.mark.asyncio
async def test_cast_vote_blocks_self_vote_across_several_entries(session: AsyncSession) -> None:
    """cast_vote checks the *target* entry's own runner_id, which already
    generalizes correctly regardless of how many entries that runner has —
    this just confirms it for a runner holding two."""
    org = await make_user(session, "org-multi4@example.com")
    runner = await make_user(session, "runner-multi4@example.com")
    contest = await _voting_contest(session, org)
    first = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.approved,
        submitted_at=PAST,
    )
    second = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.approved,
        submitted_at=PAST,
    )
    session.add_all([first, second])
    await session.flush()

    with pytest.raises(ValueError, match="свою заявку"):
        await cast_vote(session, contest, runner, first, now=NOW)
    with pytest.raises(ValueError, match="свою заявку"):
        await cast_vote(session, contest, runner, second, now=NOW)


# --- grace period --------------------------------------------------------


@pytest.mark.asyncio
async def test_submission_accepted_within_grace_window_after_close(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-grace1@example.com")
    runner = await make_user(session, "runner-grace1@example.com")
    close_at = NOW - timedelta(minutes=5)
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=close_at
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)

    # Phase has already flipped to submissions_closed for everyone...
    assert contest_phase(contest, NOW) == "submissions_closed"
    assert can_submit(contest, NOW) is False
    # ...but submit_entry itself still accepts it, undisclosed grace window.
    entry = await submit_entry(session, contest, runner, {field.id: "https://example.com"}, now=NOW)
    assert entry.status == ModerationStatus.pending


@pytest.mark.asyncio
async def test_submission_rejected_once_grace_window_elapses(session: AsyncSession) -> None:
    org = await make_user(session, "org-grace2@example.com")
    runner = await make_user(session, "runner-grace2@example.com")
    close_at = NOW - timedelta(minutes=30)
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=close_at
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)

    with pytest.raises(ValueError, match="заверш"):
        await submit_entry(session, contest, runner, {field.id: "https://example.com"}, now=NOW)


# --- voting -----------------------------------------------------


async def _voting_contest(session: AsyncSession, org):
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=PAST + timedelta(days=2),
        voting_close_at=SOON,
    )
    return contest


async def _approved_entry(session: AsyncSession, contest, runner, *, label="e") -> ContestEntry:
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=runner.id,
        status=ModerationStatus.approved,
        submitted_at=PAST,
    )
    session.add(entry)
    await session.flush()
    return entry


@pytest.mark.asyncio
async def test_cast_vote_records_a_vote(session: AsyncSession) -> None:
    org = await make_user(session, "org-vote1@example.com")
    author = await make_user(session, "author-vote1@example.com")
    voter = await make_user(session, "voter-vote1@example.com")
    contest = await _voting_contest(session, org)
    entry = await _approved_entry(session, contest, author)

    vote = await cast_vote(session, contest, voter, entry, now=NOW)
    await session.commit()

    assert vote.voter_id == voter.id
    assert vote.entry_id == entry.id
    stored = await session.scalar(select(ContestVote).where(ContestVote.id == vote.id))
    assert stored is not None


@pytest.mark.asyncio
async def test_cast_vote_blocked_outside_voting_phase(session: AsyncSession) -> None:
    org = await make_user(session, "org-vote2@example.com")
    author = await make_user(session, "author-vote2@example.com")
    voter = await make_user(session, "voter-vote2@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=PAST)
    entry = await _approved_entry(session, contest, author)

    with pytest.raises(ValueError):
        await cast_vote(session, contest, voter, entry, now=NOW)


@pytest.mark.asyncio
async def test_cast_vote_rejects_unapproved_entry(session: AsyncSession) -> None:
    org = await make_user(session, "org-vote3@example.com")
    author = await make_user(session, "author-vote3@example.com")
    voter = await make_user(session, "voter-vote3@example.com")
    contest = await _voting_contest(session, org)
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=author.id,
        status=ModerationStatus.pending,
        submitted_at=PAST,
    )
    session.add(entry)
    await session.flush()

    with pytest.raises(ValueError):
        await cast_vote(session, contest, voter, entry, now=NOW)


@pytest.mark.asyncio
async def test_cast_vote_rejects_self_vote(session: AsyncSession) -> None:
    org = await make_user(session, "org-vote4@example.com")
    author = await make_user(session, "author-vote4@example.com")
    contest = await _voting_contest(session, org)
    entry = await _approved_entry(session, contest, author)

    with pytest.raises(ValueError, match="свою"):
        await cast_vote(session, contest, author, entry, now=NOW)


@pytest.mark.asyncio
async def test_cast_vote_switches_existing_vote_instead_of_duplicating(
    session: AsyncSession,
) -> None:
    org = await make_user(session, "org-vote5@example.com")
    author1 = await make_user(session, "author-vote5a@example.com")
    author2 = await make_user(session, "author-vote5b@example.com")
    voter = await make_user(session, "voter-vote5@example.com")
    contest = await _voting_contest(session, org)
    entry1 = await _approved_entry(session, contest, author1)
    entry2 = await _approved_entry(session, contest, author2)

    await cast_vote(session, contest, voter, entry1, now=NOW)
    await cast_vote(session, contest, voter, entry2, now=NOW)
    await session.commit()

    votes = list(
        await session.scalars(
            select(ContestVote).where(
                ContestVote.contest_id == contest.id, ContestVote.voter_id == voter.id
            )
        )
    )
    assert len(votes) == 1
    assert votes[0].entry_id == entry2.id


@pytest.mark.asyncio
async def test_vote_tally_counts_per_entry(session: AsyncSession) -> None:
    org = await make_user(session, "org-vote6@example.com")
    author1 = await make_user(session, "author-vote6a@example.com")
    author2 = await make_user(session, "author-vote6b@example.com")
    voters = [await make_user(session, f"voter-vote6-{i}@example.com") for i in range(3)]
    contest = await _voting_contest(session, org)
    entry1 = await _approved_entry(session, contest, author1)
    entry2 = await _approved_entry(session, contest, author2)

    await cast_vote(session, contest, voters[0], entry1, now=NOW)
    await cast_vote(session, contest, voters[1], entry1, now=NOW)
    await cast_vote(session, contest, voters[2], entry2, now=NOW)
    await session.commit()

    tally = await vote_tally(session, contest.id)
    assert tally[entry1.id] == 2
    assert tally[entry2.id] == 1


# --- results -----------------------------------------------------


@pytest.mark.asyncio
async def test_set_placement_and_publish_results(session: AsyncSession) -> None:
    org = await make_user(session, "org-results1@example.com")
    author = await make_user(session, "author-results1@example.com")
    contest = await _voting_contest(session, org)
    entry = await _approved_entry(session, contest, author)

    await set_placement(session, entry, 1)
    await session.commit()
    assert entry.placement == 1

    assert contest.results_published_at is None
    await publish_results(session, contest, now=NOW)
    await session.commit()
    assert contest.results_published_at == NOW
