import io

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.enums import UserRole
from app.services.media_service import media_path_to_fs
from tests.factories import make_event_group, make_user


def _fake_jpeg(size: tuple[int, int] = (900, 600)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color=(120, 60, 200)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_upload_multiple_photos_generates_thumbnails(
    session: AsyncSession, client: AsyncClient
) -> None:
    org = await make_user(session, "org2@example.com", UserRole.organizer)
    event, _ = await make_event_group(session, org)
    await session.commit()

    token = create_access_token(org.id)
    files = [
        ("files", ("one.jpg", _fake_jpeg(), "image/jpeg")),
        ("files", ("two.jpg", _fake_jpeg((1200, 1200)), "image/jpeg")),
    ]
    resp = await client.post(
        f"/api/v1/events/{event.id}/photos",
        files=files,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body) == 2

    for photo in body:
        assert photo["thumbnail"]
        assert photo["thumbnail"] != photo["image"]
        thumb_fs = media_path_to_fs(photo["thumbnail"])
        assert thumb_fs.exists()
        with Image.open(thumb_fs) as img:
            assert max(img.size) <= 480

    list_resp = await client.get(f"/api/v1/events/{event.id}/photos")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2


@pytest.mark.asyncio
async def test_photo_upload_requires_organizer(
    session: AsyncSession, client: AsyncClient
) -> None:
    runner = await make_user(session, "runner-photo@example.com", UserRole.runner)
    org = await make_user(session, "org3@example.com", UserRole.organizer)
    event, _ = await make_event_group(session, org)
    await session.commit()

    token = create_access_token(runner.id)
    resp = await client.post(
        f"/api/v1/events/{event.id}/photos",
        files=[("files", ("x.jpg", _fake_jpeg(), "image/jpeg"))],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
