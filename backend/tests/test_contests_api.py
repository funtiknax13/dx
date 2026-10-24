import json
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token
from app.models.contest import ContestEntry
from app.models.enums import ContestFieldType, ModerationStatus
from tests.factories import add_contest_field, make_contest, make_user

# Unlike test_contest_service.py (which injects `now=` directly), the API
# never receives a fake "now" — contest_phase() always uses the real wall
# clock — so these have to be real-time-relative, not a fixed fictional date.
PAST = datetime.now(UTC) - timedelta(days=10)
SOON = datetime.now(UTC) + timedelta(days=1)

_IMG = ("shot.png", b"fake-image-bytes", "image/png")
_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><name>Test</name><trkseg>
    <trkpt lat="55.7500" lon="37.6200"><ele>150.0</ele><time>2026-05-01T08:00:00Z</time></trkpt>
    <trkpt lat="55.7510" lon="37.6210"><ele>152.0</ele><time>2026-05-01T08:05:00Z</time></trkpt>
  </trkseg></trk>
</gpx>"""


def _auth(user_id: int) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


async def _open_contest(session: AsyncSession, org):
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
    )
    link = await add_contest_field(
        session, contest, position=0, label="Ссылка", field_type=ContestFieldType.url
    )
    photo = await add_contest_field(
        session,
        contest,
        position=1,
        label="Фото",
        field_type=ContestFieldType.image,
        required=False,
        visible_to_voters=False,
    )
    return contest, link, photo


# --- listing / detail -----------------------------------------------------


@pytest.mark.asyncio
async def test_list_contests_only_shows_published(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi1@example.com")
    published = await make_contest(session, org, is_published=True)
    await make_contest(session, org, is_published=False)
    await session.commit()

    resp = await client.get("/api/v1/contests")
    assert resp.status_code == 200
    ids = [c["id"] for c in resp.json()]
    assert ids == [published.id]


@pytest.mark.asyncio
async def test_unpublished_contest_404s(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi2@example.com")
    draft = await make_contest(session, org, is_published=False)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{draft.id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upcoming_contest_hides_fields(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi3@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=SOON)
    await add_contest_field(session, contest)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "upcoming"
    assert body["fields"] is None


@pytest.mark.asyncio
async def test_open_contest_shows_fields(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi4@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["phase"] == "submissions_open"
    assert [f["id"] for f in body["fields"]] == [link.id, photo.id]


# --- submission -----------------------------------------------------


@pytest.mark.asyncio
async def test_submit_entry_with_text_and_file_fields(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi5@example.com")
    runner = await make_user(session, "runner-capi5@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/route"},
        files={f"field_{photo.id}": _IMG},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    values = {v["field_id"]: v["value"] for v in body["values"]}
    assert values[link.id] == "https://example.com/route"
    photo_paths = json.loads(values[photo.id])
    assert photo_paths and all(p.startswith("/media/contests/") for p in photo_paths)


@pytest.mark.asyncio
async def test_submit_entry_missing_required_field_422s(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi6@example.com")
    runner = await make_user(session, "runner-capi6@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={},
    )
    assert resp.status_code == 422
    assert str(link.id) in resp.json()["detail"]["errors"]


@pytest.mark.asyncio
async def test_resubmit_keeps_file_when_not_reuploaded(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi7@example.com")
    runner = await make_user(session, "runner-capi7@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/a"},
        files={f"field_{photo.id}": _IMG},
    )
    assert first.status_code == 201, first.text
    entry_id = first.json()["id"]
    first_photo_path = {v["field_id"]: v["value"] for v in first.json()["values"]}[photo.id]

    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={"entry_id": str(entry_id), f"field_{link.id}": "https://example.com/b"},
    )
    assert second.status_code == 201, second.text
    second_values = {v["field_id"]: v["value"] for v in second.json()["values"]}
    assert second_values[link.id] == "https://example.com/b"
    assert second_values[photo.id] == first_photo_path  # untouched


@pytest.mark.asyncio
async def test_submit_multi_select_field_stores_selection(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-ms-api1@example.com")
    runner = await make_user(session, "runner-ms-api1@example.com")
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session,
        contest,
        field_type=ContestFieldType.multi_select,
        options=["Зима", "Весна", "Лето", "Осень"],
    )
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": json.dumps(["Зима", "Лето"])},
    )
    assert resp.status_code == 201, resp.text
    values = {v["field_id"]: v["value"] for v in resp.json()["values"]}
    assert json.loads(values[field.id]) == ["Зима", "Лето"]


@pytest.mark.asyncio
async def test_submit_several_images_caps_at_configured_max(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-img-api1@example.com")
    runner = await make_user(session, "runner-img-api1@example.com")
    contest, link, photo = await _open_contest(session, org)
    await session.commit()

    too_many = settings.contest_entry_max_images + 2
    files = [
        (f"field_{photo.id}", (f"shot{i}.png", b"fake-bytes", "image/png")) for i in range(too_many)
    ]
    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/route"},
        files=files,
    )
    assert resp.status_code == 201, resp.text
    values = {v["field_id"]: v["value"] for v in resp.json()["values"]}
    paths = json.loads(values[photo.id])
    assert len(paths) == settings.contest_entry_max_images


@pytest.mark.asyncio
async def test_submit_second_entry_without_cap_creates_a_new_entry(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-multi-api1@example.com")
    runner = await make_user(session, "runner-multi-api1@example.com")
    contest, link, _photo = await _open_contest(session, org)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/a"},
    )
    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/b"},
    )
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


@pytest.mark.asyncio
async def test_submit_second_entry_blocked_once_cap_reached(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-multi-api2@example.com")
    runner = await make_user(session, "runner-multi-api2@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=SOON,
        max_entries_per_runner=1,
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": "https://example.com/a"},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": "https://example.com/b"},
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_submit_entry_blocked_outside_window(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi8@example.com")
    runner = await make_user(session, "runner-capi8@example.com")
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
    )
    field = await add_contest_field(session, contest, field_type=ContestFieldType.url)
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{field.id}": "https://example.com"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_my_entries_requires_auth_and_returns_empty_when_absent(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi9@example.com")
    runner = await make_user(session, "runner-capi9@example.com")
    contest, _link, _photo = await _open_contest(session, org)
    await session.commit()

    anon = await client.get(f"/api/v1/contests/{contest.id}/my-entries")
    assert anon.status_code == 401

    resp = await client.get(f"/api/v1/contests/{contest.id}/my-entries", headers=_auth(runner.id))
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_my_entries_lists_all_of_a_runners_entries(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi9b@example.com")
    runner = await make_user(session, "runner-capi9b@example.com")
    contest, link, _photo = await _open_contest(session, org)
    await session.commit()

    first = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/first"},
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        data={f"field_{link.id}": "https://example.com/second"},
    )
    assert second.status_code == 201, second.text

    resp = await client.get(f"/api/v1/contests/{contest.id}/my-entries", headers=_auth(runner.id))
    assert resp.status_code == 200
    ids = {e["id"] for e in resp.json()}
    assert ids == {first.json()["id"], second.json()["id"]}


# --- gpx route map -----------------------------------------------------


async def _contest_with_gpx_field(session: AsyncSession, org):
    contest = await make_contest(
        session, org, is_published=True, submissions_open_at=PAST, submissions_close_at=SOON
    )
    field = await add_contest_field(
        session, contest, field_type=ContestFieldType.gpx, required=True, visible_to_voters=True
    )
    return contest, field


@pytest.mark.asyncio
async def test_entry_route_map_visible_to_owner_while_pending(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-gpx-api1@example.com")
    runner = await make_user(session, "runner-gpx-api1@example.com")
    contest, field = await _contest_with_gpx_field(session, org)
    await session.commit()

    submit = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        files={f"field_{field.id}": ("route.gpx", _GPX.encode(), "application/gpx+xml")},
    )
    assert submit.status_code == 201, submit.text
    entry_id = submit.json()["id"]

    resp = await client.get(
        f"/api/v1/contests/{contest.id}/entries/{entry_id}/values/{field.id}/route-map",
        headers=_auth(runner.id),
    )
    assert resp.status_code == 200, resp.text
    assert len(resp.json()["track_points"]) == 2


@pytest.mark.asyncio
async def test_entry_route_map_hidden_from_others_before_approval(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-gpx-api2@example.com")
    runner = await make_user(session, "runner-gpx-api2@example.com")
    other = await make_user(session, "other-gpx-api2@example.com")
    contest, field = await _contest_with_gpx_field(session, org)
    await session.commit()

    submit = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(runner.id),
        files={f"field_{field.id}": ("route.gpx", _GPX.encode(), "application/gpx+xml")},
    )
    entry_id = submit.json()["id"]

    resp = await client.get(
        f"/api/v1/contests/{contest.id}/entries/{entry_id}/values/{field.id}/route-map",
        headers=_auth(other.id),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_entry_route_map_visible_to_anyone_once_approved_during_voting(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-gpx-api3@example.com")
    author = await make_user(session, "author-gpx-api3@example.com")
    voter = await make_user(session, "voter-gpx-api3@example.com")
    contest, field = await _contest_with_gpx_field(session, org)
    await session.commit()

    submit = await client.post(
        f"/api/v1/contests/{contest.id}/entries",
        headers=_auth(author.id),
        files={f"field_{field.id}": ("route.gpx", _GPX.encode(), "application/gpx+xml")},
    )
    assert submit.status_code == 201, submit.text
    entry_id = submit.json()["id"]

    entry = await session.get(ContestEntry, entry_id)
    assert entry is not None
    entry.status = ModerationStatus.approved
    contest.submissions_close_at = PAST + timedelta(days=1)
    contest.voting_open_at = PAST + timedelta(days=2)
    contest.voting_close_at = SOON
    await session.commit()

    resp = await client.get(
        f"/api/v1/contests/{contest.id}/entries/{entry_id}/values/{field.id}/route-map",
        headers=_auth(voter.id),
    )
    assert resp.status_code == 200, resp.text


# --- voting -----------------------------------------------------


async def _voting_contest_with_approved_entry(session: AsyncSession, org, author):
    contest = await make_contest(
        session,
        org,
        is_published=True,
        submissions_open_at=PAST,
        submissions_close_at=PAST + timedelta(days=1),
        voting_open_at=PAST + timedelta(days=2),
        voting_close_at=SOON,
    )
    field = await add_contest_field(
        session, contest, field_type=ContestFieldType.url, visible_to_voters=True
    )
    hidden_field = await add_contest_field(
        session,
        contest,
        position=1,
        label="Заметка для админа",
        field_type=ContestFieldType.text,
        required=False,
        visible_to_voters=False,
    )
    entry = ContestEntry(
        contest_id=contest.id,
        runner_id=author.id,
        status=ModerationStatus.approved,
        submitted_at=PAST,
    )
    session.add(entry)
    await session.flush()
    from app.models.contest import ContestEntryValue

    session.add(ContestEntryValue(entry_id=entry.id, field_id=field.id, value="https://x.com"))
    session.add(ContestEntryValue(entry_id=entry.id, field_id=hidden_field.id, value="secret"))
    await session.flush()
    return contest, entry, field, hidden_field


@pytest.mark.asyncio
async def test_entries_hidden_before_voting_opens(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi10@example.com")
    contest = await make_contest(session, org, is_published=True, submissions_open_at=PAST)
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}/entries")
    assert resp.status_code == 200
    assert resp.json()["entries"] == []


@pytest.mark.asyncio
async def test_entries_list_filters_hidden_fields_and_vote_counts(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi11@example.com")
    author = await make_user(session, "author-capi11@example.com")
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    await session.commit()

    resp = await client.get(f"/api/v1/contests/{contest.id}/entries")
    assert resp.status_code == 200
    body = resp.json()
    assert body["votes_visible"] is False
    assert len(body["entries"]) == 1
    entry_out = body["entries"][0]
    field_ids = [v["field_id"] for v in entry_out["values"]]
    assert field.id in field_ids
    assert hidden_field.id not in field_ids
    assert entry_out["vote_count"] is None  # votes_visible_live is off by default


@pytest.mark.asyncio
async def test_cast_vote_updates_my_vote_and_tally_when_live(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi12@example.com")
    author = await make_user(session, "author-capi12@example.com")
    voter = await make_user(session, "voter-capi12@example.com")
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    contest.votes_visible_live = True
    await session.commit()

    vote_resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries/{entry.id}/vote", headers=_auth(voter.id)
    )
    assert vote_resp.status_code == 204

    list_resp = await client.get(f"/api/v1/contests/{contest.id}/entries", headers=_auth(voter.id))
    body = list_resp.json()
    assert body["my_vote_entry_id"] == entry.id
    assert body["entries"][0]["vote_count"] == 1


@pytest.mark.asyncio
async def test_cast_vote_blocks_self_vote(session: AsyncSession, client: AsyncClient) -> None:
    org = await make_user(session, "org-capi13@example.com")
    author = await make_user(session, "author-capi13@example.com")
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries/{entry.id}/vote", headers=_auth(author.id)
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_cast_vote_requires_complete_profile(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org-capi14@example.com")
    author = await make_user(session, "author-capi14@example.com")
    incomplete_voter = await make_user(session, "voter-capi14@example.com", complete_profile=False)
    contest, entry, field, hidden_field = await _voting_contest_with_approved_entry(
        session, org, author
    )
    await session.commit()

    resp = await client.post(
        f"/api/v1/contests/{contest.id}/entries/{entry.id}/vote",
        headers=_auth(incomplete_voter.id),
    )
    assert resp.status_code == 403
