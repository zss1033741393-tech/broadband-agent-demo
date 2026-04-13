"""FastAPI 应用入口，端口 8080。

与 Gradio UI（7860）独立运行，互不干扰。
启动方式：
    cd backend
    python -m api.main
"""

import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.observability.logger import setup_logger
from api import repository as repo
from api.routes.conversations import router as conv_router
from api.routes.messages import router as msg_router
from api.routes.images import router as img_router

setup_logger()

_api_log = logger.bind(channel="api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await repo.init_db()
    logger.info("FastAPI 服务启动，端口 8080")
    yield
    logger.info("FastAPI 服务关闭")


app = FastAPI(title="家宽网络调优助手 API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """每个 HTTP 请求打一行访问日志到 api.log。

    SSE 长连接下 `elapsed_ms` 反映从进入 FastAPI 到首个响应头就绪的耗时，
    流中每个事件的详情由 `sse.log` 单独记录。
    """
    started = time.monotonic()
    path = request.url.path
    method = request.method
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = int((time.monotonic() - started) * 1000)
        _api_log.exception(f"{method} {path} → 500 elapsed_ms={elapsed_ms}")
        raise
    elapsed_ms = int((time.monotonic() - started) * 1000)
    _api_log.info(f"{method} {path} → {response.status_code} elapsed_ms={elapsed_ms}")
    return response


app.include_router(conv_router, prefix="/api")
app.include_router(msg_router, prefix="/api")
app.include_router(img_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8080, reload=True)
