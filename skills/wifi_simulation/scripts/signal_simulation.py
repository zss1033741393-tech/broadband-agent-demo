#!/usr/bin/env python3
"""
信号强度仿真脚本 (02_signal_simulation.py) - 独立自包含版本

功能：
    给定栅格地图和 AP 位置，使用 COST231 多壁传播模型，
    仿真整个栅格图中每个栅格的信号强度（RSSI）。
    支持 AP 自动优化功能：使用 K-means + 梯度上升算法。

用法：
    # 手动指定 AP 位置
    python scripts/02_signal_simulation.py --grid <grid_path> --ap "x,y" --ap "x2,y2"

    # AP 自动优化
    python scripts/02_signal_simulation.py --grid <grid_path> --ap-count 3

示例：
    # 单个 AP
    python scripts/02_signal_simulation.py \\
        --grid output/floorplan/grid_map.npy \\
        --ap 6.4,6.4 \\
        --output-dir output/signal

    # 多个 AP
    python scripts/02_signal_simulation.py \\
        --grid output/floorplan/grid_map.npy \\
        --ap 3.0,3.0 --ap 10.0,10.0 \\
        --tx-power 23 --frequency 5.0

    # AP 自动优化
    python scripts/02_signal_simulation.py \\
        --grid output/floorplan/grid_map.npy \\
        --ap-count 3 \\
        --output-dir output/signal

输出：
    - {output_dir}/rssi_matrix.npy: 信号强度矩阵（dBm）
    - {output_dir}/rssi_heatmap.png: 信号热力图可视化
    - {output_dir}/signal_stats.json: 信号统计信息
    - {output_dir}/optimized_ap_positions.json: 优化后的 AP 位置（仅自动优化时）
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import typer
from matplotlib import pyplot as plt
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from typer import Option

app = typer.Typer(
    name="signal-sim",
    help="WiFi信号强度仿真工具",
    add_completion=False,
)
console = Console()

# Material IDs aligned with 01_floorplan_process.py:
# 0=空旷, 1=砖墙, 2=门, 3=窗, 4=混凝土
MATERIALS: Dict[int, Dict[str, Any]] = {
    0: {"name": "空旷", "attenuation": 0},
    1: {"name": "砖墙", "attenuation": 12},
    2: {"name": "门", "attenuation": 3},
    3: {"name": "窗", "attenuation": 5},
    4: {"name": "混凝土", "attenuation": 25},
}

MATERIAL_COLORS: Dict[int, Tuple[int, int, int]] = {
    0: (255, 255, 255),
    1: (100, 100, 100),
    2: (139, 69, 19),
    3: (160, 82, 45),
    4: (135, 206, 235),
    5: (210, 180, 140),
}


@dataclass
class GridMap:
    grid: np.ndarray
    scale: float
    width: int = field(init=False)
    height: int = field(init=False)

    def __post_init__(self):
        if self.grid is not None:
            self.height, self.width = self.grid.shape

    @classmethod
    def from_array(cls, grid: np.ndarray, scale: float = 0.1) -> "GridMap":
        return cls(grid=grid, scale=scale)

    def meter_to_pixel(self, x: float, y: float) -> Tuple[int, int]:
        px = int(x / self.scale)
        py = int(y / self.scale)
        return (max(0, min(px, self.width - 1)), max(0, min(py, self.height - 1)))

    def pixel_to_meter(self, px: int, py: int) -> Tuple[float, float]:
        x = px * self.scale
        y = py * self.scale
        return (x, y)

    def is_valid_position(self, x: float, y: float) -> bool:
        px, py = self.meter_to_pixel(x, y)
        if px < 0 or px >= self.width or py < 0 or py >= self.height:
            return False
        return self.grid[py, px] == 0

    def get_free_space_positions(self) -> np.ndarray:
        free_mask = self.grid == 0
        y_indices, x_indices = np.where(free_mask)
        return np.column_stack([x_indices, y_indices])


def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    return points


@dataclass
class Cost231Model:
    tx_power: float = 20.0
    frequency: float = 5.0
    ap_height: float = 1.5

    def calculate_path_loss(self, distance: float, wall_attenuation: float) -> float:
        if distance < 1.0:
            fspl = 20 * np.log10(1.0) + 20 * np.log10(self.frequency * 1000) - 27.55
        else:
            fspl = 20 * np.log10(distance) + 20 * np.log10(self.frequency * 1000) - 27.55

        total_loss = fspl + wall_attenuation
        return total_loss

    def calculate_rssi(self, distance: float, wall_attenuation: float) -> float:
        path_loss = self.calculate_path_loss(distance, wall_attenuation)
        rssi = self.tx_power - path_loss
        return rssi

    def calculate_wall_attenuation(
        self, x0: float, y0: float, x1: float, y1: float, grid_map: GridMap
    ) -> float:
        px0, py0 = grid_map.meter_to_pixel(x0, y0)
        px1, py1 = grid_map.meter_to_pixel(x1, y1)

        points = bresenham_line(px0, py0, px1, py1)

        total_attenuation = 0.0
        prev_material = 0

        for px, py in points:
            if px < 0 or px >= grid_map.width or py < 0 or py >= grid_map.height:
                continue

            material_id = int(grid_map.grid[py, px])

            if material_id != prev_material and material_id != 0:
                attenuation = MATERIALS.get(material_id, {}).get("attenuation", 10)
                total_attenuation += attenuation

            prev_material = material_id

        return total_attenuation


def calculate_signal_strength(
    ap_x: float,
    ap_y: float,
    target_x: float,
    target_y: float,
    model: Cost231Model,
    grid_map: GridMap,
) -> float:
    distance = np.sqrt((target_x - ap_x) ** 2 + (target_y - ap_y) ** 2)
    distance = max(distance, 0.1)
    wall_attenuation = model.calculate_wall_attenuation(ap_x, ap_y, target_x, target_y, grid_map)
    rssi = model.calculate_rssi(distance, wall_attenuation)
    return rssi


def calculate_coverage(
    ap_positions: List[Tuple[float, float]],
    grid_map: GridMap,
    model_params: Dict[str, Any],
) -> np.ndarray:
    model = Cost231Model(
        tx_power=model_params.get("tx_power", 20.0),
        frequency=model_params.get("frequency", 5.0),
        ap_height=model_params.get("ap_height", 1.5),
    )

    rssi_matrix = np.full((grid_map.height, grid_map.width), -100.0)

    for py in range(grid_map.height):
        for px in range(grid_map.width):
            x, y = grid_map.pixel_to_meter(px, py)

            max_rssi = -100.0
            for ap_x, ap_y in ap_positions:
                rssi = calculate_signal_strength(ap_x, ap_y, x, y, model, grid_map)
                max_rssi = max(max_rssi, rssi)

            rssi_matrix[py, px] = max_rssi

    return rssi_matrix


def optimize_ap_placement(
    grid_map: GridMap,
    ap_count: int,
    model_params: Dict[str, Any],
    max_iterations: int = 100,
    step_size: float = 0.3,
    convergence_threshold: float = 0.1,
) -> Tuple[List[Tuple[float, float]], Dict[str, Any]]:
    console.print(f"[blue]开始AP自动优化，目标数量: {ap_count}[/blue]")

    ap_positions = _kmeans_initialization(grid_map, ap_count)
    console.print(f"[green]K-means初始化完成，初始位置: {ap_positions}[/green]")

    model = Cost231Model(
        tx_power=model_params.get("tx_power", 20.0),
        frequency=model_params.get("frequency", 5.0),
        ap_height=model_params.get("ap_height", 1.5),
    )

    best_min_rssi = -100.0
    best_positions = ap_positions.copy()
    no_improve_count = 0

    directions = [
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, -1),
        (-1, 0),
        (-1, 1),
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]优化AP位置...", total=max_iterations)

        for iteration in range(max_iterations):
            improved = False

            for i, (ap_x, ap_y) in enumerate(ap_positions):
                current_min_rssi = _calculate_min_rssi_for_ap(
                    i, ap_x, ap_y, ap_positions, model, grid_map
                )

                best_direction = None
                best_direction_rssi = current_min_rssi

                for dx, dy in directions:
                    new_x = ap_x + dx * step_size
                    new_y = ap_y + dy * step_size

                    if not grid_map.is_valid_position(new_x, new_y):
                        continue

                    new_min_rssi = _calculate_min_rssi_for_ap(
                        i, new_x, new_y, ap_positions, model, grid_map
                    )

                    if new_min_rssi > best_direction_rssi:
                        best_direction_rssi = new_min_rssi
                        best_direction = (dx, dy)

                if best_direction is not None:
                    new_x = ap_x + best_direction[0] * step_size
                    new_y = ap_y + best_direction[1] * step_size
                    ap_positions[i] = (new_x, new_y)
                    improved = True

            rssi_matrix = calculate_coverage(ap_positions, grid_map, model_params)
            valid_mask = grid_map.grid == 0
            overall_min_rssi = float(np.min(rssi_matrix[valid_mask]))

            if overall_min_rssi > best_min_rssi:
                improvement = overall_min_rssi - best_min_rssi
                best_min_rssi = overall_min_rssi
                best_positions = ap_positions.copy()
                no_improve_count = 0

                if improvement < convergence_threshold:
                    console.print(
                        f"[yellow]迭代 {iteration + 1}: 收敛（改进 {improvement:.3f} dB）[/yellow]"
                    )
                    break
            else:
                no_improve_count += 1
                if no_improve_count >= 10:
                    console.print(
                        f"[yellow]迭代 {iteration + 1}: 连续10次无改进，停止优化[/yellow]"
                    )
                    break

            progress.update(task, advance=1)

            if not improved:
                console.print(f"[yellow]迭代 {iteration + 1}: 无改进方向，停止优化[/yellow]")
                break
        else:
            console.print(f"[yellow]达到最大迭代次数 {max_iterations}[/yellow]")

    stats = {
        "iterations": iteration + 1,
        "final_min_rssi": round(best_min_rssi, 2),
        "final_mean_rssi": round(float(np.mean(rssi_matrix[valid_mask])), 2),
        "converged": no_improve_count >= 10 or iteration < max_iterations - 1,
    }

    console.print(f"[green]优化完成！最终最小RSSI: {best_min_rssi:.2f} dBm[/green]")

    return best_positions, stats


def _kmeans_initialization(grid_map: GridMap, ap_count: int) -> List[Tuple[float, float]]:
    free_positions = grid_map.get_free_space_positions()

    if len(free_positions) == 0:
        raise ValueError("没有可用的空旷区域")

    meter_positions = np.array([grid_map.pixel_to_meter(px, py) for px, py in free_positions])

    np.random.seed(42)
    indices = np.random.choice(len(meter_positions), size=ap_count, replace=False)
    centers = meter_positions[indices].copy()

    for _ in range(10):
        labels = np.argmin(np.linalg.norm(meter_positions[:, np.newaxis] - centers, axis=2), axis=1)

        new_centers = np.array(
            [
                meter_positions[labels == i].mean(axis=0) if np.any(labels == i) else centers[i]
                for i in range(ap_count)
            ]
        )

        if np.allclose(centers, new_centers, atol=0.01):
            break

        centers = new_centers

    final_positions = []
    for cx, cy in centers:
        if grid_map.is_valid_position(cx, cy):
            final_positions.append((float(cx), float(cy)))
        else:
            distances = np.linalg.norm(meter_positions - [cx, cy], axis=1)
            nearest_idx = np.argmin(distances)
            final_positions.append(tuple(meter_positions[nearest_idx].tolist()))

    return final_positions


def _calculate_min_rssi_for_ap(
    ap_index: int,
    ap_x: float,
    ap_y: float,
    ap_positions: List[Tuple[float, float]],
    model: Cost231Model,
    grid_map: GridMap,
) -> float:
    temp_positions = ap_positions.copy()
    temp_positions[ap_index] = (ap_x, ap_y)

    rssi_matrix = np.full((grid_map.height, grid_map.width), -100.0)

    for py in range(grid_map.height):
        for px in range(grid_map.width):
            if grid_map.grid[py, px] != 0:
                continue

            x, y = grid_map.pixel_to_meter(px, py)

            max_rssi = -100.0
            for tx, ty in temp_positions:
                rssi = calculate_signal_strength(tx, ty, x, y, model, grid_map)
                max_rssi = max(max_rssi, rssi)

            rssi_matrix[py, px] = max_rssi

    valid_mask = grid_map.grid == 0
    if np.any(valid_mask):
        return float(np.min(rssi_matrix[valid_mask]))
    return -100.0


def get_signal_quality(rssi: float) -> str:
    if rssi >= -30:
        return "excellent"
    elif rssi >= -50:
        return "good"
    elif rssi >= -70:
        return "fair"
    elif rssi >= -90:
        return "poor"
    else:
        return "very_poor"


def create_heatmap(
    rssi_matrix: np.ndarray,
    grid_map: GridMap,
    ap_positions: List[Tuple[float, float]],
    output_path: Path,
    colormap: str = "RdYlGn",
) -> None:
    fig, ax = plt.subplots(figsize=(12, 10))

    rssi_display = rssi_matrix.copy()
    rssi_display[grid_map.grid > 0] = np.nan

    vmin, vmax = -90, -30
    im = ax.imshow(
        rssi_display,
        cmap=colormap,
        vmin=vmin,
        vmax=vmax,
        interpolation="nearest",
    )

    cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("RSSI (dBm)", fontsize=12)

    for i, (ap_x, ap_y) in enumerate(ap_positions):
        ap_px, ap_py = grid_map.meter_to_pixel(ap_x, ap_y)
        ax.plot(ap_px, ap_py, "b^", markersize=15, label="AP" if i == 0 else "")
        ax.annotate(
            f"AP{i + 1}\n({ap_x:.1f}, {ap_y:.1f})",
            (ap_px, ap_py),
            xytext=(10, 10),
            textcoords="offset points",
            fontsize=8,
            color="blue",
        )

    grid_overlay = np.zeros((*grid_map.grid.shape, 4))
    for material_id, color in MATERIAL_COLORS.items():
        if material_id > 0:
            mask = grid_map.grid == material_id
            grid_overlay[mask] = [c / 255 for c in color] + [0.3]

    ax.imshow(grid_overlay, interpolation="nearest")

    real_w = grid_map.width * grid_map.scale
    real_h = grid_map.height * grid_map.scale

    ax.set_title(
        f"WiFi Signal Strength Heatmap\n"
        f"Grid: {grid_map.width}x{grid_map.height} | "
        f"Area: {real_w:.1f}m x {real_h:.1f}m | "
        f"APs: {len(ap_positions)}",
        fontsize=14,
        fontweight="bold",
    )

    tick_interval = max(1, grid_map.width // 8)
    ax.set_xticks(range(0, grid_map.width, tick_interval))
    ax.set_yticks(range(0, grid_map.height, tick_interval))
    ax.set_xticklabels(
        [f"{i * grid_map.scale:.1f}" for i in range(0, grid_map.width, tick_interval)]
    )
    ax.set_yticklabels(
        [f"{i * grid_map.scale:.1f}" for i in range(0, grid_map.height, tick_interval)]
    )
    ax.set_xlabel("Distance (m)", fontsize=11)
    ax.set_ylabel("Distance (m)", fontsize=11)

    ax.grid(True, alpha=0.3, linestyle="--")
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    console.print(f"  [green]热力图已保存: {output_path}[/green]")


def analyze_signal_distribution(rssi_matrix: np.ndarray, grid_map: GridMap) -> dict:
    valid_mask = grid_map.grid == 0
    valid_rssi = rssi_matrix[valid_mask]

    if len(valid_rssi) == 0:
        return {"error": "没有有效的信号数据"}

    quality_ranges = {
        "excellent": (-30, float("inf")),
        "good": (-50, -30),
        "fair": (-70, -50),
        "poor": (-90, -70),
        "very_poor": (float("-inf"), -90),
    }

    distribution = {}
    for quality, (min_rssi, max_rssi) in quality_ranges.items():
        count = np.sum((valid_rssi >= min_rssi) & (valid_rssi < max_rssi))
        percentage = count / len(valid_rssi) * 100
        distribution[quality] = {
            "count": int(count),
            "percentage": round(percentage, 2),
        }

    stats = {
        "mean_rssi": round(float(np.mean(valid_rssi)), 2),
        "median_rssi": round(float(np.median(valid_rssi)), 2),
        "min_rssi": round(float(np.min(valid_rssi)), 2),
        "max_rssi": round(float(np.max(valid_rssi)), 2),
        "std_rssi": round(float(np.std(valid_rssi)), 2),
        "coverage_area_m2": round(float(np.sum(valid_mask)) * grid_map.scale**2, 2),
        "quality_distribution": distribution,
    }

    return stats


@app.command()
def simulate(
    grid: Path = Option(..., "--grid", "-g", help="栅格地图文件路径 (.npy)"),
    ap: Optional[List[str]] = Option(None, "--ap", "-a", help="AP 位置坐标（米），格式: 'x,y'"),
    ap_count: Optional[int] = Option(None, "--ap-count", "-n", help="AP 数量（启用自动优化）"),
    grid_info: Optional[Path] = Option(None, "--grid-info", help="栅格信息文件路径 (.json)"),
    tx_power: float = Option(20.0, "--tx-power", "-p", help="AP 发射功率（dBm，默认: 20）"),
    frequency: float = Option(5.0, "--frequency", "-f", help="WiFi 频率（GHz，默认: 5.0）"),
    ap_height: float = Option(1.5, "--ap-height", help="AP 高度（米，默认: 1.5）"),
    output_dir: Path = Option(Path("output/signal"), "--output-dir", "-o", help="输出目录"),
    colormap: str = Option("RdYlGn", "--colormap", "-c", help="热力图颜色映射"),
    visualize: bool = Option(False, "--visualize", "-v", help="显示可视化结果"),
    fast: bool = Option(True, "--fast", help="使用快速模式（向量化计算，适合大网格）"),
) -> None:
    """
    信号强度仿真：输入栅格+AP位置，输出信号强度矩阵

    使用方式（二选一）：
    1. 手动指定AP位置: --ap "x,y" --ap "x2,y2"
    2. 自动优化AP位置: --ap-count N

    快速模式：使用 --fast 启用向量化计算，适合400x400以上大网格
    """
    console.print("=" * 60)
    console.print("[bold cyan]信号强度仿真脚本[/bold cyan]")
    console.print("=" * 60)

    if ap is None and ap_count is None:
        console.print("[red]错误：必须指定 --ap 或 --ap-count 参数之一[/red]")
        raise typer.Exit(1)

    if ap is not None and ap_count is not None:
        console.print("[yellow]警告：同时指定了 --ap 和 --ap-count，优先使用 --ap[/yellow]")

    if not grid.exists():
        console.print(f"[red]错误：栅格地图不存在: {grid}[/red]")
        raise typer.Exit(1)

    console.print(f"[blue]栅格地图: {grid}[/blue]")
    console.print(f"[blue]AP 发射功率: {tx_power} dBm[/blue]")
    console.print(f"[blue]频率: {frequency} GHz[/blue]")
    console.print(f"[blue]AP 高度: {ap_height} m[/blue]")
    console.print()

    grid_data = np.load(grid)

    scale = 0.1
    if grid_info and grid_info.exists():
        with open(grid_info, "r", encoding="utf-8") as f:
            info = json.load(f)
            scale = info.get("scale", 0.1)
    else:
        info_path = grid.parent / "grid_info.json"
        if info_path.exists():
            with open(info_path, "r", encoding="utf-8") as f:
                info = json.load(f)
                scale = info.get("scale", 0.1)

    grid_map = GridMap.from_array(grid_data, scale=scale)

    console.print(f"[green]栅格尺寸: {grid_map.width}x{grid_map.height}[/green]")
    console.print(f"[green]比例尺: {grid_map.scale:.4f} m/px[/green]")
    console.print(
        f"[green]实际面积: {grid_map.width * grid_map.scale:.1f}m x {grid_map.height * grid_map.scale:.1f}m[/green]"
    )
    console.print()

    model_params = {
        "tx_power": tx_power,
        "frequency": frequency,
        "ap_height": ap_height,
    }

    optimization_stats = None

    if ap is not None:
        ap_positions = []
        for ap_str in ap:
            try:
                x, y = map(float, ap_str.split(","))
                ap_positions.append((x, y))
            except ValueError:
                console.print(f"[red]错误：无效的AP坐标格式: {ap_str}，应为 'x,y'[/red]")
                raise typer.Exit(1)

        console.print(f"[blue]手动指定AP位置 ({len(ap_positions)} 个):[/blue]")
        for i, (x, y) in enumerate(ap_positions, 1):
            px, py = grid_map.meter_to_pixel(x, y)
            console.print(f"  AP{i}: ({x:.2f}m, {y:.2f}m) -> 栅格({px}, {py})")
    else:
        if fast:
            ap_positions, optimization_stats = optimize_ap_placement_fast(
                grid_map=grid_map,
                ap_count=ap_count,
                model_params=model_params,
            )
        else:
            ap_positions, optimization_stats = optimize_ap_placement(
                grid_map=grid_map,
                ap_count=ap_count,
                model_params=model_params,
            )

        console.print(f"[blue]自动优化后的AP位置 ({len(ap_positions)} 个):[/blue]")
        for i, (x, y) in enumerate(ap_positions, 1):
            px, py = grid_map.meter_to_pixel(x, y)
            console.print(f"  AP{i}: ({x:.2f}m, {y:.2f}m) -> 栅格({px}, {py})")

    console.print()

    console.print(f"[blue]开始计算信号覆盖{' (快速模式)' if fast else ''}...[/blue]")
    if fast:
        rssi_matrix = calculate_coverage_fast(ap_positions, grid_map, model_params)
    else:
        rssi_matrix = calculate_coverage(ap_positions, grid_map, model_params)

    console.print(
        f"[green]  RSSI 范围: {np.min(rssi_matrix):.1f} ~ {np.max(rssi_matrix):.1f} dBm[/green]"
    )
    console.print()

    output_dir.mkdir(parents=True, exist_ok=True)

    console.print("[blue]保存输出文件...[/blue]")

    rssi_path = output_dir / "rssi_matrix.npy"
    np.save(rssi_path, rssi_matrix)
    console.print(f"  [green]✓ 信号矩阵: {rssi_path}[/green]")

    ap_positions_path = output_dir / "ap_positions.json"
    with open(ap_positions_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "ap_positions": ap_positions,
                "count": len(ap_positions),
                "optimized": ap is None,
                "optimization_stats": optimization_stats,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    console.print(f"  [green]✓ AP位置: {ap_positions_path}[/green]")

    if optimization_stats:
        optimized_path = output_dir / "optimized_ap_positions.json"
        with open(optimized_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "optimized_positions": ap_positions,
                    "ap_count": len(ap_positions),
                    **optimization_stats,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )
        console.print(f"  [green]✓ 优化后AP位置: {optimized_path}[/green]")

    heatmap_path = output_dir / "rssi_heatmap.png"
    create_heatmap(rssi_matrix, grid_map, ap_positions, heatmap_path, colormap)

    console.print("[blue]分析信号分布...[/blue]")
    stats = analyze_signal_distribution(rssi_matrix, grid_map)

    stats_path = output_dir / "signal_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    console.print(f"  [green]✓ 统计信息: {stats_path}[/green]")

    console.print()
    console.print("[bold]信号质量分布:[/bold]")

    quality_names = {
        "excellent": "优 (-30dBm 以上)",
        "good": "良 (-50 ~ -30dBm)",
        "fair": "中 (-70 ~ -50dBm)",
        "poor": "差 (-90 ~ -70dBm)",
        "very_poor": "很差 (-90dBm 以下)",
    }

    quality_colors = {
        "excellent": "green",
        "good": "bright_green",
        "fair": "yellow",
        "poor": "orange",
        "very_poor": "red",
    }

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("质量等级", style="cyan")
    table.add_column("占比", justify="right")
    table.add_column("栅格数", justify="right")
    table.add_column("可视化", width=30)

    for quality, data in stats["quality_distribution"].items():
        bar = "█" * int(data["percentage"] / 3)
        color = quality_colors.get(quality, "white")
        table.add_row(
            quality_names.get(quality, quality),
            f"[bold {color}]{data['percentage']:.1f}%[/bold {color}]",
            str(data["count"]),
            f"[{color}]{bar}[/{color}]",
        )

    console.print(table)

    console.print()
    console.print("[bold]统计摘要:[/bold]")
    summary_table = Table(show_header=False, box=None)
    summary_table.add_column(style="cyan")
    summary_table.add_column()
    summary_table.add_row("平均 RSSI:", f"{stats['mean_rssi']:.1f} dBm")
    summary_table.add_row("中位数 RSSI:", f"{stats['median_rssi']:.1f} dBm")
    summary_table.add_row("最小 RSSI:", f"{stats['min_rssi']:.1f} dBm")
    summary_table.add_row("最大 RSSI:", f"{stats['max_rssi']:.1f} dBm")
    summary_table.add_row("覆盖面积:", f"{stats['coverage_area_m2']:.1f} m²")

    if optimization_stats:
        summary_table.add_row("优化迭代:", f"{optimization_stats['iterations']} 次")
        summary_table.add_row("收敛状态:", "是" if optimization_stats["converged"] else "否")

    console.print(summary_table)

    console.print()
    console.print("=" * 60)
    console.print(f"[bold green]仿真完成！输出目录: {output_dir}[/bold green]")
    console.print("=" * 60)


# ============================================================================
# 优化版函数 (向量化计算，大幅提升性能)
# ============================================================================


def _estimate_wall_attenuation_vectorized(
    wall_grid: np.ndarray,
    ap_x: float,
    ap_y: float,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
) -> np.ndarray:
    height, width = wall_grid.shape
    attenuation = np.zeros((height, width), dtype=np.float32)

    # Distance in meters from AP to each pixel
    dx = x_coords - ap_x
    dy = y_coords - ap_y
    distance = np.sqrt(dx**2 + dy**2) + 1e-6

    # Average weighted attenuation per wall type
    # Based on typical indoor floorplan wall density
    WEIGHTED_WALL_ATTEN = 4.0  # 平均每米穿墙衰减 (dB/m)

    # 基础穿墙衰减：与距离成正比
    attenuation = WEIGHTED_WALL_ATTEN * distance

    # 额外衰减：墙体密集区域的像素额外衰减
    WALL_DENSITY_BONUS = 2.0  # 位于墙体像素的额外加成
    wall_mask = wall_grid > 0
    attenuation += wall_mask.astype(np.float32) * WALL_DENSITY_BONUS * (distance / 10.0)

    return attenuation


def calculate_coverage_fast(
    ap_positions: List[Tuple[float, float]],
    grid_map: GridMap,
    model_params: Dict[str, Any],
) -> np.ndarray:
    tx_power = model_params.get("tx_power", 20.0)
    frequency = model_params.get("frequency", 5.0)

    height, width = grid_map.height, grid_map.width

    y_coords, x_coords = np.meshgrid(np.arange(height), np.arange(width), indexing="ij")

    x_meters = x_coords * grid_map.scale
    y_meters = y_coords * grid_map.scale

    rssi_matrix = np.full((height, width), -100.0)

    for ap_x, ap_y in ap_positions:
        distances = np.sqrt((x_meters - ap_x) ** 2 + (y_meters - ap_y) ** 2)
        distances = np.maximum(distances, 0.1)

        if frequency < 1.0:
            fspl = 20 * np.log10(1.0) + 20 * np.log10(frequency * 1000) - 27.55
        else:
            fspl = 20 * np.log10(distances) + 20 * np.log10(frequency * 1000) - 27.55

        wall_attenuation = _estimate_wall_attenuation_vectorized(
            grid_map.grid, ap_x, ap_y, x_meters, y_meters
        )

        total_loss = fspl + wall_attenuation
        rssi = tx_power - total_loss

        rssi_matrix = np.maximum(rssi_matrix, rssi)

    return rssi_matrix


def _calculate_min_rssi_fast(
    ap_index: int,
    ap_x: float,
    ap_y: float,
    ap_positions: List[Tuple[float, float]],
    grid_map: GridMap,
    model_params: Dict[str, Any],
) -> float:
    temp_positions = ap_positions.copy()
    temp_positions[ap_index] = (ap_x, ap_y)

    rssi_matrix = calculate_coverage_fast(temp_positions, grid_map, model_params)

    valid_mask = grid_map.grid == 0
    if np.any(valid_mask):
        return float(np.min(rssi_matrix[valid_mask]))
    return -100.0


def _is_valid_ap_position(grid_map: GridMap, x: float, y: float) -> bool:
    px, py = grid_map.meter_to_pixel(x, y)
    if 0 <= px < grid_map.width and 0 <= py < grid_map.height:
        return grid_map.grid[py, px] == 0
    return False


def _kmeans_initialization_fast(grid_map: GridMap, ap_count: int) -> List[Tuple[float, float]]:
    from sklearn.cluster import KMeans

    free_space = []
    for y in range(grid_map.height):
        for x in range(grid_map.width):
            if grid_map.grid[y, x] == 0:
                mx, my = grid_map.pixel_to_meter(x, y)
                free_space.append([mx, my])

    if len(free_space) < ap_count:
        positions = []
        for i in range(ap_count):
            px = (i + 1) * grid_map.width // (ap_count + 1)
            py = grid_map.height // 2
            mx, my = grid_map.pixel_to_meter(px, py)
            positions.append((float(mx), float(my)))
        return positions

    free_space = np.array(free_space)

    kmeans = KMeans(n_clusters=ap_count, random_state=42, n_init=10)
    kmeans.fit(free_space)

    positions = []
    for cx, cy in kmeans.cluster_centers_:
        px, py = grid_map.meter_to_pixel(cx, cy)
        if 0 <= px < grid_map.width and 0 <= py < grid_map.height and grid_map.grid[py, px] == 0:
            positions.append((float(cx), float(cy)))
        else:
            distances = np.linalg.norm(free_space - [cx, cy], axis=1)
            nearest = free_space[np.argmin(distances)]
            positions.append((float(nearest[0]), float(nearest[1])))

    return positions


def optimize_ap_placement_fast(
    grid_map: GridMap,
    ap_count: int,
    model_params: Dict[str, Any],
    max_iterations: int = 30,
    step_size: float = 0.5,
    convergence_threshold: float = 0.2,
) -> Tuple[List[Tuple[float, float]], Dict[str, Any]]:
    console.print(f"[blue]开始AP优化 (快速模式)，目标: {ap_count}个AP[/blue]")

    ap_positions = _kmeans_initialization_fast(grid_map, ap_count)
    console.print(f"[green]K-means初始化: {ap_positions}[/green]")

    best_min_rssi = -100.0
    best_positions = ap_positions.copy()
    no_improve_count = 0

    directions = [
        (0, 1),
        (1, 1),
        (1, 0),
        (1, -1),
        (0, -1),
        (-1, -1),
        (-1, 0),
        (-1, 1),
    ]

    for iteration in range(max_iterations):
        improved = False

        for i, (ap_x, ap_y) in enumerate(ap_positions):
            current_min_rssi = _calculate_min_rssi_fast(
                i, ap_x, ap_y, ap_positions, grid_map, model_params
            )

            best_direction = None
            best_direction_rssi = current_min_rssi

            for dx, dy in directions:
                new_x = ap_x + dx * step_size
                new_y = ap_y + dy * step_size

                if not _is_valid_ap_position(grid_map, new_x, new_y):
                    continue

                new_min_rssi = _calculate_min_rssi_fast(
                    i, new_x, new_y, ap_positions, grid_map, model_params
                )

                if new_min_rssi > best_direction_rssi:
                    best_direction_rssi = new_min_rssi
                    best_direction = (dx, dy)

            if best_direction is not None:
                new_x = ap_x + best_direction[0] * step_size
                new_y = ap_y + best_direction[1] * step_size
                ap_positions[i] = (new_x, new_y)
                improved = True

        rssi_matrix = calculate_coverage_fast(ap_positions, grid_map, model_params)
        valid_mask = grid_map.grid == 0
        overall_min_rssi = float(np.min(rssi_matrix[valid_mask]))

        if overall_min_rssi > best_min_rssi:
            improvement = overall_min_rssi - best_min_rssi
            best_min_rssi = overall_min_rssi
            best_positions = ap_positions.copy()
            no_improve_count = 0

            if improvement < convergence_threshold:
                console.print(f"[yellow]迭代 {iteration + 1}: 收敛[/yellow]")
                break
        else:
            no_improve_count += 1
            if no_improve_count >= 5:
                console.print(f"[yellow]迭代 {iteration + 1}: 早停[/yellow]")
                break

    return best_positions, {
        "min_rssi": best_min_rssi,
        "iterations": iteration + 1,
        "converged": improvement < convergence_threshold if improved else False,
    }


if __name__ == "__main__":
    app()
