"""统一日志初始化模块 — 使用 loguru。

其他模块直接 `from loguru import logger` 即可，
只需在应用启动时 import 本模块一次完成 sink 配置。
"""

import sys
from pathlib import Path

from loguru import logger

_LOG_DIR = Path(__file__).resolve().parents[2] / "data" / "logs" / "app"


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

    logger.info("日志系统初始化完成")
