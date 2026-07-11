import os
import tempfile
import uuid
from collections.abc import AsyncGenerator

# Configure the environment BEFORE importing anything that reads settings, so the
# global engine/session bind to a throwaway SQLite file instead of Postgres.
_TMP = tempfile.mkdtemp(prefix="dh-test-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP}/test-{uuid.uuid4().hex}.db"
os.environ["MEDIA_ROOT"] = os.path.join(_TMP, "media")
os.environ["MEDIA_URL"] = "/media"
os.environ["EMAIL_BACKEND"] = "console"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["ADMIN_SECRET_KEY"] = "test-admin-secret"
os.makedirs(os.environ["MEDIA_ROOT"], exist_ok=True)

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.core.db import SessionLocal, engine  # noqa: E402
from app.models import Base  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def _create_schema() -> AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # Dispose so no pooled connection stays bound to this test's (now closing) event loop.
    await engine.dispose()


@pytest_asyncio.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as s:
        yield s


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    # Import here so schema fixture and env are already applied.
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
