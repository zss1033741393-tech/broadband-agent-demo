#!/usr/bin/env python3
"""WIFI 仿真 3 阶段流水线 — 编排器。

作为 agno Skill 脚本被调用，串行执行：
  1. 户型图处理 → grid_map + simplified_floorplan.png
  2. 信号强度仿真 → rssi_matrix + rssi_heatmap.png
  3. 网络性能仿真 → network_dashboard.png + metrics

最终输出 JSON（含 image_paths + metrics + summary）到 stdout。
中间步骤的 print/console 日志重定向到 stderr，不污染 JSON 输出。
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 重定向 stdout → stderr，使导入模块的 print/console.print 不混入 JSON ──
_ORIG_STDOUT = sys.stdout
sys.stdout = sys.stderr

# ── 脚本目录加入 sys.path，便于导入兄弟模块 ──
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPTS_DIR.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

import numpy as np  # noqa: E402, I001
from floorplan_process import process_floorplan  # noqa: E402
from network_simulation import process_network_simulation  # noqa: E402
from signal_simulation import (  # noqa: E402
    GridMap as SigGridMap,
    analyze_signal_distribution,
    calculate_coverage_fast,
    create_heatmap,
    optimize_ap_placement_fast,
)  # noqa: E402

# ── 默认参数 ──
_DEFAULTS: Dict[str, Any] = {
    "ap_count": 2,
    "tx_power": 20,
    "frequency": 5.0,
    "wifi_standard": "wifi6",
    "grid_size": 400,
}


def _resolve_floorplan_image(params: Dict[str, Any]) -> Path:
    """确定户型图图片路径：优先用户指定，其次内置样例。"""
    image_path = params.get("floor_plan_image")
    if image_path:
        p = Path(image_path)
        if p.exists():
            return p
    sample = _SKILL_DIR / "references" / "sample_floorplan.jpg"
    if sample.exists():
        return sample
    raise FileNotFoundError(
        "未找到户型图图片，请提供 floor_plan_image 参数或将样例图放入 references/"
    )


def _run_step1_floorplan(
    params: Dict[str, Any], output_base: Path
) -> tuple[Dict[str, Any], List[Dict[str, str]]]:
    """阶段 1：户型图处理。"""
    step: Dict[str, Any] = {"step": 1, "name": "户型图处理", "status": "pending"}
    images: List[Dict[str, str]] = []
    try:
        floorplan_image = _resolve_floorplan_image(params)
        floorplan_output = output_base / "floorplan"
        grid_map = process_floorplan(
            input_image=floorplan_image,
            output_dir=floorplan_output,
            grid_size=params.get("grid_size", 400),
            use_dl=True,
        )
        step["status"] = "success"
        step["result"] = {
            "grid_size": f"{grid_map.width}x{grid_map.height}",
            "scale": f"{grid_map.scale:.4f} m/px",
            "real_area": f"{grid_map.width * grid_map.scale:.1f}m x {grid_map.height * grid_map.scale:.1f}m",
        }
        vis_path = floorplan_output / "simplified_floorplan.png"
        if vis_path.exists():
            images.append({"label": "户型识别", "path": str(vis_path)})
    except Exception as e:
        step["status"] = "error"
        step["error"] = str(e)
    return step, images


def _run_step2_signal(
    params: Dict[str, Any], output_base: Path
) -> tuple[Dict[str, Any], List[Dict[str, str]], Dict[str, Any]]:
    """阶段 2：信号强度仿真。"""
    step: Dict[str, Any] = {"step": 2, "name": "信号强度仿真", "status": "pending"}
    images: List[Dict[str, str]] = []
    metrics: Dict[str, Any] = {}

    grid_map_path = output_base / "floorplan" / "grid_map.npy"
    if not grid_map_path.exists():
        step["status"] = "skipped"
        step["error"] = "Step 1 未产出 grid_map.npy"
        return step, images, metrics

    try:
        grid_data = np.load(grid_map_path)

        # 读取 grid_info 获取比例尺
        scale = 0.05
        grid_info_path = output_base / "floorplan" / "grid_info.json"
        if grid_info_path.exists():
            with open(grid_info_path, encoding="utf-8") as f:
                info = json.load(f)
                scale = info.get("scale", 0.05)

        sig_grid = SigGridMap.from_array(grid_data, scale=scale)
        signal_output = output_base / "signal"
        signal_output.mkdir(parents=True, exist_ok=True)

        model_params = {
            "tx_power": params.get("tx_power", 20),
            "frequency": params.get("frequency", 5.0),
            "ap_height": 1.5,
        }

        # AP 位置：手动指定 vs 自动优化
        ap_positions_raw = params.get("ap_positions")
        optimization_stats: Optional[Dict[str, Any]] = None
        if ap_positions_raw:
            ap_positions = []
            for ap_str in ap_positions_raw:
                x, y = map(float, ap_str.split(","))
                ap_positions.append((x, y))
        else:
            ap_count = params.get("ap_count", 2)
            ap_positions, optimization_stats = optimize_ap_placement_fast(
                grid_map=sig_grid,
                ap_count=ap_count,
                model_params=model_params,
            )

        # 计算信号覆盖
        rssi_matrix = calculate_coverage_fast(ap_positions, sig_grid, model_params)
        np.save(signal_output / "rssi_matrix.npy", rssi_matrix)

        # 保存 AP 位置
        with open(signal_output / "ap_positions.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "ap_positions": ap_positions,
                    "count": len(ap_positions),
                    "optimized": ap_positions_raw is None,
                    "optimization_stats": optimization_stats,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        # 生成热力图
        heatmap_path = signal_output / "rssi_heatmap.png"
        create_heatmap(rssi_matrix, sig_grid, ap_positions, heatmap_path)
        if heatmap_path.exists():
            images.append({"label": "信号热力图", "path": str(heatmap_path)})

        # 信号分析
        stats = analyze_signal_distribution(rssi_matrix, sig_grid)
        with open(signal_output / "signal_stats.json", "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

        step["status"] = "success"
        step["result"] = {
            "ap_count": len(ap_positions),
            "ap_positions": [f"({x:.1f}, {y:.1f})" for x, y in ap_positions],
            "mean_rssi": stats.get("mean_rssi"),
            "min_rssi": stats.get("min_rssi"),
            "coverage_area_m2": stats.get("coverage_area_m2"),
        }
        metrics = stats

    except Exception as e:
        step["status"] = "error"
        step["error"] = str(e)

    return step, images, metrics


def _run_step3_network(
    params: Dict[str, Any], output_base: Path
) -> tuple[Dict[str, Any], List[Dict[str, str]], Dict[str, Any]]:
    """阶段 3：网络性能仿真。"""
    step: Dict[str, Any] = {"step": 3, "name": "网络性能仿真", "status": "pending"}
    images: List[Dict[str, str]] = []
    metrics: Dict[str, Any] = {}

    rssi_path = output_base / "signal" / "rssi_matrix.npy"
    grid_path = output_base / "floorplan" / "grid_map.npy"

    if not rssi_path.exists() or not grid_path.exists():
        step["status"] = "skipped"
        step["error"] = "Step 2 未产出 rssi_matrix.npy"
        return step, images, metrics

    try:
        network_output = output_base / "network"
        process_network_simulation(
            rssi_path=rssi_path,
            grid_path=grid_path,
            output_dir=network_output,
            standard=params.get("wifi_standard", "wifi6"),
        )

        dashboard_path = network_output / "network_dashboard.png"
        if dashboard_path.exists():
            images.append({"label": "网络仪表盘", "path": str(dashboard_path)})

        metrics_path = network_output / "network_metrics.json"
        if metrics_path.exists():
            with open(metrics_path, encoding="utf-8") as f:
                net_metrics = json.load(f)
            metrics = net_metrics
            step["result"] = {
                "mean_throughput_mbps": net_metrics.get("throughput", {}).get("mean_mbps"),
                "mean_latency_ms": net_metrics.get("latency", {}).get("mean_ms"),
                "mean_packet_loss_pct": net_metrics.get("packet_loss", {}).get("mean_percent"),
            }

        step["status"] = "success"

    except Exception as e:
        step["status"] = "error"
        step["error"] = str(e)

    return step, images, metrics


def simulate(params_json: str = "{}") -> str:
    """执行 WIFI 仿真 3 阶段流水线。"""
    try:
        params = json.loads(params_json) if params_json else {}
    except json.JSONDecodeError:
        return json.dumps({"error": "参数 JSON 解析失败", "status": "error"}, ensure_ascii=False)

    merged = {**_DEFAULTS, **params}

    # 输出目录
    run_id = uuid.uuid4().hex[:8]
    output_base = _SKILL_DIR / "data" / f"run_{run_id}"
    output_base.mkdir(parents=True, exist_ok=True)

    all_steps: List[Dict[str, Any]] = []
    all_images: List[Dict[str, str]] = []
    all_metrics: Dict[str, Any] = {}

    # ---- Step 1 ----
    step1, imgs1 = _run_step1_floorplan(merged, output_base)
    all_steps.append(step1)
    all_images.extend(imgs1)

    # ---- Step 2 ----
    step2, imgs2, sig_metrics = _run_step2_signal(merged, output_base)
    all_steps.append(step2)
    all_images.extend(imgs2)
    if sig_metrics:
        all_metrics["signal"] = sig_metrics

    # ---- Step 3 ----
    step3, imgs3, net_metrics = _run_step3_network(merged, output_base)
    all_steps.append(step3)
    all_images.extend(imgs3)
    if net_metrics:
        all_metrics["network"] = net_metrics

    # ---- 汇总 ----
    summary_parts: List[str] = []
    if step1.get("status") == "success":
        summary_parts.append("户型识别完成")
    if step2.get("status") == "success":
        r = step2.get("result", {})
        summary_parts.append(
            f"{r.get('ap_count', '?')} AP 自动选点，平均 RSSI {r.get('mean_rssi', '?')} dBm"
        )
    if step3.get("status") == "success":
        r = step3.get("result", {})
        summary_parts.append(
            f"平均吞吐量 {r.get('mean_throughput_mbps', '?')} Mbps, "
            f"延迟 {r.get('mean_latency_ms', '?')} ms"
        )

    overall_status = "ok" if all(s["status"] == "success" for s in all_steps) else "partial"

    result = {
        "skill": "wifi_simulation",
        "status": overall_status,
        "steps": all_steps,
        "image_paths": all_images,
        "metrics": all_metrics,
        "summary": "；".join(summary_parts) if summary_parts else "仿真未完成",
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _params = sys.argv[1] if len(sys.argv) > 1 else "{}"
    _result = simulate(_params)
    # 恢复原始 stdout，输出最终 JSON
    _ORIG_STDOUT.write(_result + "\n")
    _ORIG_STDOUT.flush()
