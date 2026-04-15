#!/usr/bin/env python3
"""WIFI 仿真 Skill 入口 — 参数映射 + 结果打包薄外壳。

职责：
1. 解析 Provisioning 传入的单个 JSON 参数字符串；
2. 调用 `home_wifi_engine.generate_ap_optimization_comparison` 产出
   2 张对比 PNG + 4 份 JSON 矩阵（补点前/后 × RSSI/卡顿率）；
3. 吞掉引擎内部一切 stdout/stderr（warnings、progress），仅向原始 stdout
   输出一行结构化 JSON；
4. 读取 engine 产出的 JSON 数据文件，抽出摘要 `stats` 拼进返回对象；
   矩阵本体（`.data` 字段）不进 stdout，由 event_adapter 后续按需内联。
"""

from __future__ import annotations

import io
import json
import os
import sys
import uuid
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

# ─── sys.path 注入，保证 engine 可 import ───────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

# 先把原始 stdout 锁住，再 import engine（engine 内部 matplotlib 初始化可能打 warning）
_ORIG_STDOUT = sys.stdout
_ORIG_STDERR = sys.stderr

_SILENT_STDOUT = io.StringIO()
_SILENT_STDERR = io.StringIO()

with redirect_stdout(_SILENT_STDOUT), redirect_stderr(_SILENT_STDERR):
    import home_wifi_engine as _engine  # type: ignore  # noqa: E402


# ─── 常量 ───────────────────────────────────────────────────────────────────────

_SKILL_DIR = _SCRIPT_DIR.parent
_DATA_DIR = _SKILL_DIR / "data"

_VALID_PRESETS = {"一居室", "两居室", "三居室", "大平层"}

_DEFAULTS: dict[str, Any] = {
    "preset": "大平层",
    "ap_count": 1,
    "grid_size": 40,
    "target_ap_count": 3,
    "show_doors": True,
}


# ─── 参数校验 ─────────────────────────────────────────────────────────────────

def _validate(params: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    preset = params.get("preset")
    if preset not in _VALID_PRESETS:
        errors.append(f"preset 必须是 {sorted(_VALID_PRESETS)} 之一，当前={preset!r}")
    ap = params.get("ap_count")
    if not isinstance(ap, int) or ap < 1:
        errors.append(f"ap_count 必须是 >=1 的整数，当前={ap!r}")
    grid = params.get("grid_size")
    if not isinstance(grid, int) or grid < 10 or grid > 120:
        errors.append(f"grid_size 必须在 [10, 120]，当前={grid!r}")
    target = params.get("target_ap_count")
    if not isinstance(target, int) or target <= ap:
        errors.append(f"target_ap_count 必须是 > ap_count 的整数，当前={target!r}")
    return errors


# ─── JSON 摘要抽取 ─────────────────────────────────────────────────────────────

def _stats_from_json(path: Path) -> dict[str, Any]:
    """读 engine 产出的矩阵 JSON，只取摘要字段（不含 data 大矩阵）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for k in ("mean_rssi", "worst_rssi", "mean_stall_rate", "max_stall_rate", "shape"):
        if k in payload:
            out[k] = payload[k]
    return out


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def _run(params: dict[str, Any]) -> dict[str, Any]:
    run_id = uuid.uuid4().hex[:8]
    out_dir = _DATA_DIR / f"run_{run_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    preset = params["preset"]
    ap = params["ap_count"]
    grid = params["grid_size"]
    target_ap = params["target_ap_count"]
    show_doors = bool(params.get("show_doors", True))

    # 始终产出：2 张对比 PNG + 4 份 JSON 矩阵（补点前/后 × RSSI/卡顿率）
    result = _engine.generate_ap_optimization_comparison(
        preset, ap, target_ap, str(out_dir), grid_size=grid, show_doors=show_doors
    )
    image_paths: list[dict[str, str]] = [
        {"label": "RSSI 对比图(补点前/后)", "path": result["rssi_comparison"], "kind": "rssi"},
        {"label": "卡顿率对比图(补点前/后)", "path": result["stall_comparison"], "kind": "stall"},
    ]
    data_paths: list[dict[str, str]] = [
        {"label": "补点前 RSSI 矩阵", "path": result["rssi_before_json"], "kind": "rssi", "phase": "before"},
        {"label": "补点后 RSSI 矩阵", "path": result["rssi_after_json"], "kind": "rssi", "phase": "after"},
        {"label": "补点前 卡顿率矩阵", "path": result["stall_before_json"], "kind": "stall", "phase": "before"},
        {"label": "补点后 卡顿率矩阵", "path": result["stall_after_json"], "kind": "stall", "phase": "after"},
    ]
    stats: dict[str, Any] = {
        "rssi_before": _stats_from_json(Path(result["rssi_before_json"])),
        "rssi_after": _stats_from_json(Path(result["rssi_after_json"])),
        "stall_before": _stats_from_json(Path(result["stall_before_json"])),
        "stall_after": _stats_from_json(Path(result["stall_after_json"])),
    }

    summary = _build_summary(preset, ap, target_ap, stats)
    return {
        "skill": "wifi_simulation",
        "status": "ok",
        "preset": preset,
        "grid_size": grid,
        "ap_count": ap,
        "target_ap_count": target_ap,
        "image_paths": image_paths,
        "data_paths": data_paths,
        "stats": stats,
        "summary": summary,
    }


def _build_summary(
    preset: str,
    ap: int,
    target_ap: int,
    stats: dict[str, Any],
) -> str:
    mean_b = stats.get("rssi_before", {}).get("mean_rssi")
    mean_a = stats.get("rssi_after", {}).get("mean_rssi")
    # engine 保存的 stall_rate 是 0~1 分数，展示需 ×100
    stall_b = stats.get("stall_before", {}).get("mean_stall_rate")
    stall_a = stats.get("stall_after", {}).get("mean_stall_rate")
    segs = [f"{preset} {ap}AP→{target_ap}AP 补点优化完成"]
    if isinstance(mean_b, (int, float)) and isinstance(mean_a, (int, float)):
        segs.append(f"平均 RSSI 由 {mean_b:.1f} dBm 提升至 {mean_a:.1f} dBm")
    if isinstance(stall_b, (int, float)) and isinstance(stall_a, (int, float)):
        segs.append(f"平均卡顿率由 {stall_b * 100:.2f}% 降至 {stall_a * 100:.2f}%")
    return "；".join(segs)


def main(argv: list[str]) -> int:
    raw = argv[1] if len(argv) > 1 else "{}"
    try:
        user_params = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        err = {"skill": "wifi_simulation", "status": "error", "message": f"参数 JSON 解析失败: {exc}"}
        _ORIG_STDOUT.write(json.dumps(err, ensure_ascii=False) + "\n")
        _ORIG_STDOUT.flush()
        return 1
    if not isinstance(user_params, dict):
        err = {"skill": "wifi_simulation", "status": "error", "message": "参数必须是 JSON 对象"}
        _ORIG_STDOUT.write(json.dumps(err, ensure_ascii=False) + "\n")
        _ORIG_STDOUT.flush()
        return 1

    merged = {**_DEFAULTS, **user_params}
    errs = _validate(merged)
    if errs:
        err = {"skill": "wifi_simulation", "status": "error", "message": "参数校验失败", "errors": errs}
        _ORIG_STDOUT.write(json.dumps(err, ensure_ascii=False) + "\n")
        _ORIG_STDOUT.flush()
        return 1

    # 再次锁定 stdout/stderr，engine 内任何打印都静音
    silent_out = io.StringIO()
    silent_err = io.StringIO()
    try:
        with redirect_stdout(silent_out), redirect_stderr(silent_err):
            # 禁掉 numpy 警告（engine 内部可能触发）
            os.environ.setdefault("PYTHONWARNINGS", "ignore")
            result = _run(merged)
    except Exception as exc:  # noqa: BLE001
        err = {"skill": "wifi_simulation", "status": "error", "message": f"仿真执行失败: {exc}"}
        _ORIG_STDOUT.write(json.dumps(err, ensure_ascii=False) + "\n")
        _ORIG_STDOUT.flush()
        return 1

    _ORIG_STDOUT.write(json.dumps(result, ensure_ascii=False) + "\n")
    _ORIG_STDOUT.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
