"""JD 输入（受控链接抓取与截图 OCR）预览 API。"""

from typing import Annotated

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, StringConstraints

from app.apps.api.dependencies.common import get_current_user
from app.apps.api.dependencies.opportunity import get_jd_input_adapter, get_jd_ocr_adapter
from app.domain.identity import User
from app.ports.jd_input import (
    JdImageInput,
    JdInputKind,
    JdInputPort,
    JdUrlInput,
)

router = APIRouter(prefix="/job-postings", tags=["job-inputs"])

UrlField = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2_048)]


class FetchJobPostingRequest(BaseModel):
    """受控链接抓取的 URL 输入。"""

    url: UrlField


class JdInputPreviewResponse(BaseModel):
    """抓取成功后的正文预览，供用户确认后再进入既有创建路径。"""

    jd_text: str
    source_url: str | None
    kind: JdInputKind


@router.post("/fetch", response_model=JdInputPreviewResponse)
async def fetch_job_posting_preview(
    payload: FetchJobPostingRequest,
    user: User = Depends(get_current_user),
    adapter: JdInputPort = Depends(get_jd_input_adapter),
) -> JdInputPreviewResponse:
    """受控抓取 URL 并返回正文预览，不直接创建岗位快照。"""

    result = await adapter.fetch_url(JdUrlInput(payload.url))
    return JdInputPreviewResponse(
        jd_text=result.jd_text,
        source_url=result.source_url,
        kind=result.kind,
    )


@router.post("/image", response_model=JdInputPreviewResponse)
async def ocr_job_posting_image(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    adapter: JdInputPort = Depends(get_jd_ocr_adapter),
) -> JdInputPreviewResponse:
    """对截图做 OCR 并返回正文预览，不直接创建岗位快照。"""

    content = await file.read()
    result = await adapter.extract_image(
        JdImageInput(content=content, media_type=file.content_type or "application/octet-stream")
    )
    return JdInputPreviewResponse(
        jd_text=result.jd_text,
        source_url=result.source_url,
        kind=result.kind,
    )
