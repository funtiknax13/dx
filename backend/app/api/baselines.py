from fastapi import APIRouter, HTTPException, UploadFile, status

from app.api.deps import AdminUser, SessionDep
from app.schemas.baseline import BaselineCsvImportResponse
from app.services.baseline_import_service import import_baseline_csv

router = APIRouter(tags=["baselines"])


@router.post(
    "/runner-baselines/import-csv",
    response_model=BaselineCsvImportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def import_csv(
    _admin: AdminUser, session: SessionDep, file: UploadFile
) -> BaselineCsvImportResponse:
    content = await file.read()
    try:
        result = await import_baseline_csv(session, content)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    await session.commit()
    return BaselineCsvImportResponse(
        created=result.created,
        updated=result.updated,
        skipped_empty=result.skipped_empty,
        skipped_invalid_number=result.skipped_invalid_number,
        auto_matched=result.auto_matched,
        guests_created=result.guests_created,
        guests_reused=result.guests_reused,
        merged_redirects=result.merged_redirects,
    )
