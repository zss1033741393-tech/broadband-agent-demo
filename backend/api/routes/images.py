"""GET /api/images/:imageId"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(prefix="/images", tags=["images"])

_IMAGES_DIR = Path(__file__).resolve().parents[2] / "data" / "images"


@router.get("/{image_id}")
async def get_image(image_id: str):
    for ext in ("png", "jpg", "jpeg", "gif", "webp"):
        path = _IMAGES_DIR / f"{image_id}.{ext}"
        if path.exists():
            return FileResponse(path)
    return JSONResponse(status_code=404, content={"code": 1003, "message": "图片资源不存在"})
