#!/usr/bin/env python3
"""
网络体验仿真脚本 (03_network_simulation.py)

功能：
    基于信号强度矩阵，自动仿真对应的网络吞吐量、延迟、丢包率等指标，
    模拟真实的 WiFi 网络体验。

用法：
    python scripts/03_network_simulation.py --rssi <rssi_path> --grid <grid_path> [options]

示例：
    python scripts/03_network_simulation.py -r output/signal/rssi_matrix.npy -g output/floorplan/grid_map.npy
    python scripts/03_network_simulation.py -r rssi.npy -g grid.npy --standard wifi6 --bandwidth 80

输出：
    - {output_dir}/throughput_map.npy: 吞吐量矩阵（Mbps）
    - {output_dir}/latency_map.npy: 延迟矩阵（ms）
    - {output_dir}/packet_loss_map.npy: 丢包率矩阵（%）
    - {output_dir}/network_metrics.json: 网络指标统计
    - {output_dir}/network_dashboard.png: 网络指标可视化看板
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import typer
from matplotlib import pyplot as plt
from typing_extensions import Annotated

# 材质类型定义（用于可视化）
MATERIAL_COLORS: Dict[int, list] = {
    0: [255, 255, 255],  # 白色-空旷
    1: [128, 128, 128],  # 灰色-砖墙
    2: [139, 69, 19],  # 棕色-门
    3: [135, 206, 235],  # 浅蓝色-窗
    4: [64, 64, 64],  # 深灰色-混凝土
}


@dataclass
class GridMap:
    """栅格地图数据结构。"""

    grid: np.ndarray
    scale: float
    width: int
    height: int

    def is_obstacle(self, x: int, y: int) -> bool:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y, x] > 0
        return False


@dataclass
class NetworkMetrics:
    """网络性能指标。"""

    rssi: float
    snr: float
    throughput_mbps: float
    latency_ms: float
    packet_loss_percent: float
    mcs_index: int
    phy_rate_mbps: float
    quality_level: str


class WifiNetworkSimulator:
    """WiFi 网络仿真器。"""

    MCS_TABLE_WIFI6_80MHZ = [
        (35, 11, 1201.0, "5/6"),
        (30, 10, 1081.3, "5/6"),
        (25, 9, 960.7, "5/6"),
        (22, 8, 864.7, "5/6"),
        (20, 7, 720.6, "5/6"),
        (18, 6, 600.4, "3/4"),
        (15, 5, 480.4, "3/4"),
        (12, 4, 360.3, "3/4"),
        (9, 3, 240.2, "1/2"),
        (6, 2, 180.2, "1/2"),
        (3, 1, 120.1, "1/2"),
        (0, 0, 60.0, "1/2"),
        (-10, 0, 30.0, "1/2"),
    ]

    STANDARD_SCALE = {
        "wifi4": 0.55,
        "wifi5": 0.78,
        "wifi6": 1.0,
        "wifi6e": 1.0,
        "wifi7": 1.15,
    }

    AIRTIME_EFF = {
        "wifi4": (0.55, 0.55),
        "wifi5": (0.65, 0.70),
        "wifi6": (0.78, 0.83),
        "wifi6e": (0.78, 0.83),
        "wifi7": (0.82, 0.88),
    }

    CODE_RATE_EFF = {
        "1/2": 0.50,
        "2/3": 0.67,
        "3/4": 0.75,
        "5/6": 0.83,
    }

    def __init__(
        self,
        noise_floor: float = -95.0,
        multipath_fading: float = 3.0,
        standard: str = "wifi6",
        bandwidth: int = 80,
        spatial_streams: int = 2,
        mu_mimo_enabled: bool = True,
        sta_count: int = 1,
        interference_ratio: float = 10.0,
        retry_rate: float = 2.0,
        guard_interval: int = 800,
    ):
        self.noise_floor = noise_floor
        self.multipath_fading = multipath_fading
        self.standard = standard
        self.bandwidth = bandwidth
        self.spatial_streams = spatial_streams
        self.mu_mimo_enabled = mu_mimo_enabled
        self.sta_count = max(sta_count, 1)
        self.interference_ratio = interference_ratio
        self.retry_rate = retry_rate
        self.guard_interval = guard_interval

    def calculate_snr(self, rssi: float) -> float:
        fading_loss = 10.0 * math.log10(1.0 + self.multipath_fading)
        return rssi - self.noise_floor - fading_loss

    def lookup_mcs(self, snr: float) -> Tuple[int, float, str]:
        base_rate = 30.0
        mcs = 0
        code_rate = "1/2"

        for snr_thresh, mcs_idx, rate, cr in self.MCS_TABLE_WIFI6_80MHZ:
            if snr >= snr_thresh:
                base_rate = rate
                mcs = mcs_idx
                code_rate = cr
                break

        bw_scale = self.bandwidth / 80.0
        std_scale = self.STANDARD_SCALE.get(self.standard, 1.0)

        return mcs, base_rate * bw_scale * std_scale, code_rate

    def calculate_contention_factor(self) -> float:
        if self.standard in ("wifi6", "wifi6e", "wifi7"):
            alpha = 0.15
        else:
            alpha = 0.3

        factor = 1.0 + alpha * math.log(self.sta_count)

        if self.guard_interval >= 800:
            factor *= 1.05
        else:
            factor *= 0.95

        return max(factor, 1.0)

    def simulate(self, rssi: float) -> NetworkMetrics:
        snr = self.calculate_snr(rssi)
        mcs, phy_rate, code_rate = self.lookup_mcs(snr)

        std = self.standard
        eff_pair = self.AIRTIME_EFF.get(std, (0.70, 0.75))
        airtime_eff = eff_pair[1] if self.mu_mimo_enabled else eff_pair[0]

        contention = self.calculate_contention_factor()
        code_eff = self.CODE_RATE_EFF.get(code_rate, 0.75)

        throughput = (
            phy_rate
            * self.spatial_streams
            * (1.0 - self.interference_ratio / 100.0)
            * (1.0 - self.retry_rate / 100.0)
            * airtime_eff
            / contention
            * code_eff
        )

        if snr >= 35:
            latency = 3
            packet_loss = 0.1
        elif snr >= 25:
            latency = 5
            packet_loss = 0.5
        elif snr >= 15:
            latency = 10
            packet_loss = 2.0
        elif snr >= 5:
            latency = 25
            packet_loss = 5.0
        else:
            latency = 80
            packet_loss = 15.0

        if self.sta_count > 1:
            latency *= 1 + 0.1 * math.log(self.sta_count)
            packet_loss *= 1 + 0.05 * self.sta_count

        if rssi >= -30:
            quality = "excellent"
        elif rssi >= -50:
            quality = "good"
        elif rssi >= -70:
            quality = "fair"
        else:
            quality = "poor"

        return NetworkMetrics(
            rssi=rssi,
            snr=snr,
            throughput_mbps=max(throughput, 0),
            latency_ms=latency,
            packet_loss_percent=min(packet_loss, 100),
            mcs_index=mcs,
            phy_rate_mbps=phy_rate,
            quality_level=quality,
        )


def load_data(
    rssi_path: Path, grid_path: Path, grid_info_path: Optional[Path] = None
) -> Tuple[np.ndarray, GridMap]:
    """加载 RSSI 矩阵和栅格地图。"""
    if not rssi_path.exists():
        raise FileNotFoundError(f"RSSI 矩阵不存在: {rssi_path}")
    if not grid_path.exists():
        raise FileNotFoundError(f"栅格地图不存在: {grid_path}")

    rssi_matrix = np.load(rssi_path)
    grid = np.load(grid_path)

    scale = 0.1
    if grid_info_path and grid_info_path.exists():
        with open(grid_info_path, "r", encoding="utf-8") as f:
            info = json.load(f)
            scale = info.get("scale", 0.1)
    else:
        auto_info_path = grid_path.parent / "grid_info.json"
        if auto_info_path.exists():
            with open(auto_info_path, "r", encoding="utf-8") as f:
                info = json.load(f)
                scale = info.get("scale", 0.1)

    height, width = grid.shape
    grid_map = GridMap(grid=grid, scale=scale, width=width, height=height)

    return rssi_matrix, grid_map


def simulate_network(
    rssi_matrix: np.ndarray,
    grid_map: GridMap,
    simulator: WifiNetworkSimulator,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, List[NetworkMetrics]]:
    """仿真网络性能。"""
    throughput_map = np.zeros_like(rssi_matrix)
    latency_map = np.zeros_like(rssi_matrix)
    packet_loss_map = np.zeros_like(rssi_matrix)
    metrics_list = []

    total = grid_map.height * grid_map.width
    processed = 0

    print(f"  处理 {total} 个栅格...")

    for y in range(grid_map.height):
        for x in range(grid_map.width):
            if grid_map.is_obstacle(x, y):
                throughput_map[y, x] = np.nan
                latency_map[y, x] = np.nan
                packet_loss_map[y, x] = np.nan
            else:
                rssi = rssi_matrix[y, x]
                metrics = simulator.simulate(rssi)
                throughput_map[y, x] = metrics.throughput_mbps
                latency_map[y, x] = metrics.latency_ms
                packet_loss_map[y, x] = metrics.packet_loss_percent
                metrics_list.append(metrics)

            processed += 1
            if processed % 10000 == 0:
                print(f"    进度: {processed}/{total} ({100 * processed / total:.1f}%)")

    return throughput_map, latency_map, packet_loss_map, metrics_list


def create_dashboard(
    rssi_matrix: np.ndarray,
    throughput_map: np.ndarray,
    latency_map: np.ndarray,
    packet_loss_map: np.ndarray,
    grid_map: GridMap,
    output_path: Path,
) -> None:
    """创建网络性能仪表板。"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 12))

    valid_mask = grid_map.grid == 0

    # RSSI
    ax1 = axes[0, 0]
    rssi_display = rssi_matrix.copy()
    rssi_display[~valid_mask] = np.nan
    im1 = ax1.imshow(rssi_display, cmap="RdYlGn", vmin=-90, vmax=-30)
    ax1.set_title("信号强度 (RSSI)", fontsize=12, fontweight="bold")
    plt.colorbar(im1, ax=ax1, fraction=0.046, pad=0.04, label="dBm")

    # Throughput
    ax2 = axes[0, 1]
    tp_display = throughput_map.copy()
    tp_display[~valid_mask] = np.nan
    im2 = ax2.imshow(tp_display, cmap="YlGn", vmin=0, vmax=1000)
    ax2.set_title("吞吐量", fontsize=12, fontweight="bold")
    plt.colorbar(im2, ax=ax2, fraction=0.046, pad=0.04, label="Mbps")

    # Latency
    ax3 = axes[1, 0]
    lat_display = latency_map.copy()
    lat_display[~valid_mask] = np.nan
    im3 = ax3.imshow(lat_display, cmap="YlOrRd_r", vmin=0, vmax=100)
    ax3.set_title("延迟", fontsize=12, fontweight="bold")
    plt.colorbar(im3, ax=ax3, fraction=0.046, pad=0.04, label="ms")

    # Packet Loss
    ax4 = axes[1, 1]
    pl_display = packet_loss_map.copy()
    pl_display[~valid_mask] = np.nan
    im4 = ax4.imshow(pl_display, cmap="Reds", vmin=0, vmax=20)
    ax4.set_title("丢包率", fontsize=12, fontweight="bold")
    plt.colorbar(im4, ax=ax4, fraction=0.046, pad=0.04, label="%")

    for ax in axes.flat:
        ax.set_xticks([])
        ax.set_yticks([])

    plt.suptitle("WiFi 网络性能仪表板", fontsize=16, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.96])

    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close()

    print(f"  网络看板已保存: {output_path}")


def analyze_network_metrics(metrics_list: List[NetworkMetrics]) -> dict:
    """分析网络指标。"""
    if not metrics_list:
        return {"error": "没有有效的网络数据"}

    throughputs = [m.throughput_mbps for m in metrics_list]
    latencies = [m.latency_ms for m in metrics_list]
    packet_losses = [m.packet_loss_percent for m in metrics_list]
    snrs = [m.snr for m in metrics_list]

    quality_counts = {"excellent": 0, "good": 0, "fair": 0, "poor": 0}
    for m in metrics_list:
        quality_counts[m.quality_level] += 1

    total = len(metrics_list)
    quality_dist = {
        k: {"count": v, "percentage": round(v / total * 100, 2)} for k, v in quality_counts.items()
    }

    return {
        "throughput": {
            "mean_mbps": round(float(np.mean(throughputs)), 2),
            "median_mbps": round(float(np.median(throughputs)), 2),
            "min_mbps": round(float(np.min(throughputs)), 2),
            "max_mbps": round(float(np.max(throughputs)), 2),
            "std_mbps": round(float(np.std(throughputs)), 2),
        },
        "latency": {
            "mean_ms": round(float(np.mean(latencies)), 2),
            "median_ms": round(float(np.median(latencies)), 2),
            "min_ms": round(float(np.min(latencies)), 2),
            "max_ms": round(float(np.max(latencies)), 2),
            "std_ms": round(float(np.std(latencies)), 2),
        },
        "packet_loss": {
            "mean_percent": round(float(np.mean(packet_losses)), 2),
            "median_percent": round(float(np.median(packet_losses)), 2),
            "min_percent": round(float(np.min(packet_losses)), 2),
            "max_percent": round(float(np.max(packet_losses)), 2),
            "std_percent": round(float(np.std(packet_losses)), 2),
        },
        "snr": {
            "mean_db": round(float(np.mean(snrs)), 2),
            "median_db": round(float(np.median(snrs)), 2),
            "min_db": round(float(np.min(snrs)), 2),
            "max_db": round(float(np.max(snrs)), 2),
        },
        "quality_distribution": quality_dist,
        "coverage_percent": round(total / (400 * 400) * 100, 2),
    }


def process_network_simulation(
    rssi_path: Path,
    grid_path: Path,
    output_dir: Path,
    grid_info_path: Optional[Path] = None,
    standard: str = "wifi6",
    bandwidth: int = 80,
    spatial_streams: int = 2,
    mu_mimo: bool = True,
    sta_count: int = 1,
    interference: float = 10.0,
    retry_rate: float = 2.0,
    visualize: bool = False,
) -> None:
    """处理网络仿真的主函数。"""
    print("=" * 60)
    print("网络体验仿真脚本 (Typer Edition)")
    print("=" * 60)

    print("加载数据...")
    rssi_matrix, grid_map = load_data(rssi_path, grid_path, grid_info_path)
    print(f"  RSSI 矩阵: {rssi_matrix.shape}")
    print(f"  栅格地图: {grid_map.width}x{grid_map.height}")
    print()

    print("仿真参数:")
    print(f"  WiFi 标准: {standard}")
    print(f"  信道带宽: {bandwidth} MHz")
    print(f"  空间流: {spatial_streams}")
    print(f"  MU-MIMO: {'启用' if mu_mimo else '禁用'}")
    print(f"  STA 数量: {sta_count}")
    print(f"  干扰比例: {interference}%")
    print(f"  重传率: {retry_rate}%")
    print()

    simulator = WifiNetworkSimulator(
        standard=standard,
        bandwidth=bandwidth,
        spatial_streams=spatial_streams,
        mu_mimo_enabled=mu_mimo,
        sta_count=sta_count,
        interference_ratio=interference,
        retry_rate=retry_rate,
    )

    print("开始网络仿真...")
    throughput_map, latency_map, packet_loss_map, metrics_list = simulate_network(
        rssi_matrix, grid_map, simulator
    )
    print(f"  仿真完成，处理了 {len(metrics_list)} 个栅格")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)

    print("保存输出文件...")

    np.save(output_dir / "throughput_map.npy", throughput_map)
    print("  ✓ 吞吐量矩阵")

    np.save(output_dir / "latency_map.npy", latency_map)
    print("  ✓ 延迟矩阵")

    np.save(output_dir / "packet_loss_map.npy", packet_loss_map)
    print("  ✓ 丢包率矩阵")

    dashboard_path = output_dir / "network_dashboard.png"
    create_dashboard(
        rssi_matrix,
        throughput_map,
        latency_map,
        packet_loss_map,
        grid_map,
        dashboard_path,
    )

    print("分析网络指标...")
    stats = analyze_network_metrics(metrics_list)

    stats_path = output_dir / "network_metrics.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    print(f"  ✓ 网络指标: {stats_path}")

    print()
    print("=" * 60)
    print("网络性能摘要")
    print("=" * 60)
    print()

    tp_stats = stats["throughput"]
    print("吞吐量:")
    print(f"  平均: {tp_stats['mean_mbps']:.1f} Mbps")
    print(f"  中位数: {tp_stats['median_mbps']:.1f} Mbps")
    print(f"  范围: {tp_stats['min_mbps']:.1f} ~ {tp_stats['max_mbps']:.1f} Mbps")
    print()

    lat_stats = stats["latency"]
    print("延迟:")
    print(f"  平均: {lat_stats['mean_ms']:.1f} ms")
    print(f"  中位数: {lat_stats['median_ms']:.1f} ms")
    print()

    pl_stats = stats["packet_loss"]
    print("丢包率:")
    print(f"  平均: {pl_stats['mean_percent']:.2f}%")
    print(f"  中位数: {pl_stats['median_percent']:.2f}%")
    print()

    print("体验质量分布:")
    quality_labels = {
        "excellent": "极佳",
        "good": "良好",
        "fair": "一般",
        "poor": "较差",
    }
    for quality, data in stats["quality_distribution"].items():
        bar = "█" * int(data["percentage"] / 2)
        print(f"  {quality_labels.get(quality, quality)}: {data['percentage']:5.1f}% {bar}")

    print()
    print("=" * 60)
    print(f"仿真完成！输出目录: {output_dir}")
    print("=" * 60)

    if visualize:
        print()
        print("显示可视化结果...")
        img = cv2.imread(str(dashboard_path))
        cv2.imshow("Network Dashboard", img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()


app = typer.Typer(help="网络体验仿真：输入信号强度，输出吞吐量/延迟/丢包率")


@app.command()
def simulate(
    rssi: Annotated[Path, typer.Option("--rssi", "-r", help="RSSI 矩阵文件 (.npy)")] = ...,
    grid: Annotated[Path, typer.Option("--grid", "-g", help="栅格地图文件 (.npy)")] = ...,
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="输出目录")] = Path(
        "output/network"
    ),
    grid_info: Annotated[
        Optional[Path], typer.Option("--grid-info", help="栅格信息文件 (.json)")
    ] = None,
    standard: Annotated[str, typer.Option("--standard", "-s", help="WiFi 标准")] = "wifi6",
    bandwidth: Annotated[int, typer.Option("--bandwidth", "-b", help="信道带宽 (MHz)")] = 80,
    spatial_streams: Annotated[int, typer.Option("--spatial-streams", help="空间流数量")] = 2,
    mu_mimo: Annotated[bool, typer.Option("--mu-mimo/--no-mu-mimo", help="启用 MU-MIMO")] = True,
    sta_count: Annotated[int, typer.Option("--sta-count", "-n", help="STA 数量")] = 1,
    interference: Annotated[
        float, typer.Option("--interference", "-i", help="干扰比例 (%)")
    ] = 10.0,
    retry_rate: Annotated[float, typer.Option("--retry-rate", help="重传率 (%)")] = 2.0,
    visualize: Annotated[bool, typer.Option("--visualize", "-v", help="显示可视化结果")] = False,
):
    """基于信号强度矩阵仿真网络性能指标。"""
    process_network_simulation(
        rssi_path=rssi,
        grid_path=grid,
        output_dir=output_dir,
        grid_info_path=grid_info,
        standard=standard,
        bandwidth=bandwidth,
        spatial_streams=spatial_streams,
        mu_mimo=mu_mimo,
        sta_count=sta_count,
        interference=interference,
        retry_rate=retry_rate,
        visualize=visualize,
    )


if __name__ == "__main__":
    app()
