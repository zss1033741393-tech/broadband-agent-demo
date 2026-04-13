"""统一日志初始化模块 — 使用 loguru。

其他模块直接 `from loguru import logger` 即可，
只需在应用启动时 import 本模块一次完成 sink 配置。

Sink 布局（data/logs/app/ 下）：
  - app.log        — 全量 INFO+，按天滚动（总览）
  - debug.log      — 全量 DEBUG+，按天滚动（排障）
  - api.log        — 仅 api 层日志（channel="api"），按天滚动
  - sse.log        — 仅 SSE 事件（channel="sse"），按大小滚动（高频写入）

通过 `logger.bind(channel="api")` / `logger.bind(channel="sse")` 路由到专用 sink。
"""

import sys
from pathlib import Path

from loguru import logger

_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "app"


def _channel_filter(target: str):
    """构造 loguru filter：仅放行 extra.channel == target 的记录。"""
    def _f(record: dict) -> bool:
        return record["extra"].get("channel") == target
    return _f


def setup_logger() -> None:
    """初始化 loguru sinks（幂等，重复调用不会重复添加）。"""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # 移除默认 stderr handler，重新添加带格式的
    logger.remove()

    # stderr — INFO 及以上
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
        "<level>{message}</level>",
        colorize=True,
    )

    # app.log — INFO 及以上，按天滚动
    logger.add(
        str(_LOG_DIR / "app.log"),
        level="INFO",
        rotation="1 day",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    # debug.log — DEBUG 级别，按天滚动
    logger.add(
        str(_LOG_DIR / "debug.log"),
        level="DEBUG",
        rotation="1 day",
        retention="3 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    )

    # api.log — 仅 api 层（channel="api"），按天滚动
    logger.add(
        str(_LOG_DIR / "api.log"),
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        encoding="utf-8",
        filter=_channel_filter("api"),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
        "conv={extra[conv_id]} msg={extra[msg_id]} | "
        "{name}:{function}:{line} - {message}",
    )

    # sse.log — 仅 SSE 事件（channel="sse"），按大小滚动，高频写
    logger.add(
        str(_LOG_DIR / "sse.log"),
        level="DEBUG",
        rotation="20 MB",
        retention=5,
        encoding="utf-8",
        filter=_channel_filter("sse"),
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "conv={extra[conv_id]} msg={extra[msg_id]} | "
        "{message}",
    )

    # 为 api/sse sink 的 extra 字段提供默认值，避免未 bind 时 KeyError
    logger.configure(extra={"conv_id": "-", "msg_id": "-", "channel": ""})

    logger.info("日志系统初始化完成")
