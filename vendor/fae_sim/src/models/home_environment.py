"""家庭环境仿真模块。

提供户型图建模、AP 放置、WiFi 信号热力图仿真（含墙体衰减）、STA 位置信号计算、
RTMP 卡顿率热力图仿真，以及 AP 补点推荐。
"""

from __future__ import annotations

import copy as _copy
import math
from dataclasses import dataclass, field

import numpy as np


# ── 户型预设 ──

@dataclass
class Wall:
    """墙体线段。"""
    x1: float; y1: float
    x2: float; y2: float
    attenuation_db: float = 6.0   # 单面墙衰减 (dB)
    label: str = ""


@dataclass
class Room:
    """房间区域。"""
    name: str
    x: float; y: float           # 左下角
    w: float; h: float           # 宽高 (米)


@dataclass
class AP:
    """接入点。"""
    x: float; y: float
    tx_power_dbm: float = 10.0   # 发射功率 dBm
    label: str = "AP"


@dataclass
class STA:
    """终端设备。"""
    x: float; y: float
    label: str = "STA"


@dataclass
class FloorPlan:
    """户型平面图。"""
    name: str
    width: float                 # 总宽 (米)
    height: float                # 总高 (米)
    rooms: list[Room] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    aps: list[AP] = field(default_factory=list)
    stas: list[STA] = field(default_factory=list)


# ── 预设户型 ──

def create_one_bedroom() -> FloorPlan:
    """一居室 ~50m²: 客厅+卧室+厨卫。"""
    fp = FloorPlan(name="一居室", width=8, height=6)
    fp.rooms = [
        Room("客厅", 0, 0, 5, 6),
        Room("卧室", 5, 3, 3, 3),
        Room("厨卫", 5, 0, 3, 3),
    ]
    fp.walls = [
        # 外墙 (承重墙, 高衰减)
        Wall(0, 0, 8, 0, 10, "南外墙"), Wall(8, 0, 8, 6, 10, "东外墙"),
        Wall(8, 6, 0, 6, 10, "北外墙"), Wall(0, 6, 0, 0, 10, "西外墙"),
        # 内墙
        Wall(5, 0, 5, 6, 6, "客厅-东墙"),
        Wall(5, 3, 8, 3, 4, "卧室-厨卫隔墙"),
    ]
    fp.aps = [AP(2.5, 3.0, label="AP1")]
    return fp


def create_two_bedroom() -> FloorPlan:
    """两居室 ~80m²: 客厅+主卧+次卧+厨房+卫生间。"""
    fp = FloorPlan(name="两居室", width=10, height=8)
    fp.rooms = [
        Room("客厅", 0, 0, 6, 5),
        Room("厨房", 6, 0, 4, 3),
        Room("卫生间", 6, 3, 4, 2),
        Room("主卧", 0, 5, 5, 3),
        Room("次卧", 5, 5, 5, 3),
    ]
    fp.walls = [
        Wall(0, 0, 10, 0, 10, ""), Wall(10, 0, 10, 8, 10, ""),
        Wall(10, 8, 0, 8, 10, ""), Wall(0, 8, 0, 0, 10, ""),
        Wall(6, 0, 6, 5, 6, "客厅-厨房"),
        Wall(6, 3, 10, 3, 4, "厨房-卫生间"),
        Wall(0, 5, 10, 5, 6, "南-北隔墙"),
        Wall(5, 5, 5, 8, 6, "主卧-次卧"),
    ]
    fp.aps = [AP(3.0, 2.5, label="AP1")]
    return fp


def create_three_bedroom() -> FloorPlan:
    """三居室 ~120m²: 客厅+主卧+次卧1+次卧2+厨房+卫生间。"""
    fp = FloorPlan(name="三居室", width=12, height=10)
    fp.rooms = [
        Room("客厅", 0, 0, 7, 5),
        Room("厨房", 7, 0, 5, 3),
        Room("卫生间", 7, 3, 5, 2),
        Room("主卧", 0, 5, 4, 5),
        Room("次卧1", 4, 5, 4, 5),
        Room("次卧2", 8, 5, 4, 5),
    ]
    fp.walls = [
        Wall(0, 0, 12, 0, 10, ""), Wall(12, 0, 12, 10, 10, ""),
        Wall(12, 10, 0, 10, 10, ""), Wall(0, 10, 0, 0, 10, ""),
        Wall(7, 0, 7, 5, 6, ""),
        Wall(7, 3, 12, 3, 4, ""),
        Wall(0, 5, 12, 5, 6, ""),
        Wall(4, 5, 4, 10, 6, ""),
        Wall(8, 5, 8, 10, 6, ""),
    ]
    fp.aps = [AP(3.5, 2.5, label="AP1")]
    return fp


def create_large_flat() -> FloorPlan:
    """大平层 ~180m²: 开放客餐厅+主卧套+次卧×2+书房+厨房+卫×2。"""
    fp = FloorPlan(name="大平层", width=15, height=12)
    fp.rooms = [
        Room("客餐厅", 0, 0, 9, 6),
        Room("厨房", 9, 0, 6, 4),
        Room("卫生间1", 9, 4, 3, 2),
        Room("书房", 12, 4, 3, 2),
        Room("主卧", 0, 6, 5, 6),
        Room("主卫", 5, 6, 3, 3),
        Room("次卧1", 5, 9, 5, 3),
        Room("次卧2", 10, 6, 5, 6),
    ]
    fp.walls = [
        Wall(0, 0, 15, 0, 10, ""), Wall(15, 0, 15, 12, 10, ""),
        Wall(15, 12, 0, 12, 10, ""), Wall(0, 12, 0, 0, 10, ""),
        Wall(9, 0, 9, 6, 6, ""),
        Wall(9, 4, 15, 4, 4, ""),
        Wall(12, 4, 12, 6, 4, ""),
        Wall(0, 6, 15, 6, 6, ""),
        Wall(5, 6, 5, 12, 6, ""),
        Wall(5, 9, 10, 9, 4, ""),
        Wall(10, 6, 10, 12, 6, ""),
    ]
    fp.aps = [AP(4.5, 3.0, label="AP1")]
    return fp


PRESETS: dict[str, callable] = {
    "一居室": create_one_bedroom,
    "两居室": create_two_bedroom,
    "三居室": create_three_bedroom,
    "大平层": create_large_flat,
}


# ── 信号传播模型 ──

def _segments_intersect(
    ax1: float, ay1: float, ax2: float, ay2: float,
    bx1: float, by1: float, bx2: float, by2: float,
) -> bool:
    """完整线段相交判断（含共线、端点重合、线段重叠）。

    原实现仅做跨立实验，共线/端点接触时漏判，导致墙体衰减漏算。
    """
    def ccw(ox: float, oy: float, px: float, py: float, qx: float, qy: float) -> float:
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    def on_segment(px: float, py: float,
                   x1: float, y1: float, x2: float, y2: float) -> bool:
        eps = 1e-9
        return (min(x1, x2) - eps <= px <= max(x1, x2) + eps and
                min(y1, y2) - eps <= py <= max(y1, y2) + eps)

    c1 = ccw(ax1, ay1, ax2, ay2, bx1, by1)
    c2 = ccw(ax1, ay1, ax2, ay2, bx2, by2)
    c3 = ccw(bx1, by1, bx2, by2, ax1, ay1)
    c4 = ccw(bx1, by1, bx2, by2, ax2, ay2)

    # 标准跨立实验
    if (c1 * c2 < 0) and (c3 * c4 < 0):
        return True

    # 共线情形：某端点落在另一线段上即算相交
    if c1 == 0.0 and on_segment(bx1, by1, ax1, ay1, ax2, ay2):
        return True
    if c2 == 0.0 and on_segment(bx2, by2, ax1, ay1, ax2, ay2):
        return True
    if c3 == 0.0 and on_segment(ax1, ay1, bx1, by1, bx2, by2):
        return True
    if c4 == 0.0 and on_segment(ax2, ay2, bx1, by1, bx2, by2):
        return True

    return False


def count_wall_crossings(fp: FloorPlan, x1: float, y1: float, x2: float, y2: float) -> list[Wall]:
    """计算从 (x1,y1) 到 (x2,y2) 穿过的墙体列表。"""
    crossed = []
    for w in fp.walls:
        if _segments_intersect(x1, y1, x2, y2, w.x1, w.y1, w.x2, w.y2):
            crossed.append(w)
    return crossed


def signal_strength_at(fp: FloorPlan, ap: AP, x: float, y: float, freq_ghz: float = 5.0) -> float:
    """计算指定位置的信号强度 (dBm)。

    使用自由空间路径损耗 + 墙体穿透衰减模型。
    修复：限制最小路径损耗为 0（而非最小距离），防止近距离出现负 FSPL 导致
    信号强度超过发射功率的物理错误。
    """
    dist = math.hypot(x - ap.x, y - ap.y)

    # 自由空间路径损耗 (FSPL)，最小值限制为 0（物理上路径损耗不可为负）
    fspl_raw = 20 * math.log10(max(dist, 1e-6)) + 20 * math.log10(freq_ghz * 1e9) - 147.55
    fspl = max(fspl_raw, 0.0)

    # 墙体衰减
    walls = count_wall_crossings(fp, ap.x, ap.y, x, y)
    wall_loss = sum(w.attenuation_db for w in walls)

    return ap.tx_power_dbm - fspl - wall_loss


def compute_heatmap(
    fp: FloorPlan,
    resolution: float = 0.2,
    freq_ghz: float = 5.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """计算全屋信号强度热力图。

    Returns:
        (X_grid, Y_grid, RSSI_grid) — 各点信号强度 (dBm)，多 AP 取最大值。
    """
    nx = int(fp.width / resolution) + 1
    ny = int(fp.height / resolution) + 1
    xs = np.linspace(0, fp.width, nx)
    ys = np.linspace(0, fp.height, ny)
    X, Y = np.meshgrid(xs, ys)
    rssi = np.full_like(X, -120.0)

    for ap in fp.aps:
        for j in range(ny):
            for i in range(nx):
                s = signal_strength_at(fp, ap, xs[i], ys[j], freq_ghz)
                rssi[j, i] = max(rssi[j, i], s)

    return X, Y, rssi


def average_rssi(fp: FloorPlan, freq_ghz: float = 5.0) -> float:
    """全屋平均信号强度 (dBm)。"""
    _, _, rssi = compute_heatmap(fp, resolution=0.5, freq_ghz=freq_ghz)
    return float(np.mean(rssi))


def rssi_at_sta(fp: FloorPlan, sta: STA, freq_ghz: float = 5.0) -> float:
    """STA 所在位置的最优信号强度 (dBm)。"""
    best = -120.0
    for ap in fp.aps:
        s = signal_strength_at(fp, ap, sta.x, sta.y, freq_ghz)
        best = max(best, s)
    return best


# ── RTMP 卡顿率热力图 ──────────────────────────────────────────────────────────

def compute_stall_heatmap(
    fp: FloorPlan,
    base_params,
    engine,
    resolution: float = 1.0,
    freq_ghz: float = 5.0,
    progress_cb=None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """在每个网格点基于 WiFi 信号强度运行短时 RTMP 仿真，输出卡顿率网格。

    性能优化：相同 RSSI（0.5 dBm 量化）复用仿真结果。

    Args:
        fp:           户型平面图（含 AP 布局）
        base_params:  基础仿真参数 (SimParams)
        engine:       SimulationEngine 实例
        resolution:   网格分辨率（米），默认 1.0m
        progress_cb:  可选回调 callable(done, total)

    Returns:
        (X_grid, Y_grid, stall_rate_grid) — 各点卡顿率 [0, 1]
    """
    nx = int(fp.width / resolution) + 1
    ny = int(fp.height / resolution) + 1
    xs = np.linspace(0, fp.width, nx)
    ys = np.linspace(0, fp.height, ny)
    X, Y = np.meshgrid(xs, ys)
    stall = np.zeros((ny, nx))

    # 最短合法仿真时长：10 秒 = 2000 步（5ms/step）
    quick_p = _copy.deepcopy(base_params)
    quick_p.sim_duration = 10
    # 其余参数（PON 带宽、码率等）与 RTMP 仿真保持完全一致，
    # 仅逐格改写 wifi_rssi，使热力图反映 WiFi+PON 联合约束下的空间分布。

    # RSSI → stall_rate 缓存（0.5 dBm 量化，大幅减少实际仿真次数）
    _cache: dict[float, float] = {}
    total = nx * ny
    done = 0

    for j in range(ny):
        for i in range(nx):
            # 该格最优 RSSI（多 AP 取最大）
            best = -120.0
            for ap in fp.aps:
                s = signal_strength_at(fp, ap, float(xs[i]), float(ys[j]), freq_ghz)
                best = max(best, s)
            # 钳位到合法范围，0.5 dBm 量化
            rssi_key = round(float(np.clip(best, -90.0, -20.0)) * 2) / 2.0

            if rssi_key not in _cache:
                p = _copy.copy(quick_p)
                p.wifi_rssi = rssi_key
                summary, _, _ = engine.simulate(p, collect_timeseries=False)
                # 存为小数 [0, 1]：下游 _stall_to_color / recommend_ap_positions
                # 均期望小数，显示时再 ×100 得百分比。
                _cache[rssi_key] = summary.rtmp_stall_rate / 100.0

            stall[j, i] = _cache[rssi_key]
            done += 1
            if progress_cb is not None:
                progress_cb(done, total)

    return X, Y, stall


# ── AP 补点推荐 ────────────────────────────────────────────────────────────────

def recommend_ap_positions(
    fp: FloorPlan,
    rssi_grid: np.ndarray,
    stall_grid: np.ndarray,
    resolution: float = 1.0,
    n_recommend: int = 2,
    rssi_threshold: float = -70.0,
    stall_threshold: float = 0.05,
    min_dist: float = 15.0,
) -> list[dict]:
    """基于信号强度和卡顿率热力图，贪心推荐新增 AP 位置。

    综合评分：RSSI 弱覆盖(50%) + 卡顿率高(50%)。已推荐/现有 AP
    周边 min_dist 米内不重复推荐。

    Returns:
        list of {"x", "y", "rssi", "stall_rate", "score", "label"}
    """
    # 对 rssi_grid 降采样到 stall_grid 同分辨率
    ny, nx = stall_grid.shape
    xs = np.linspace(0, fp.width, nx)
    ys = np.linspace(0, fp.height, ny)

    if rssi_grid.shape != stall_grid.shape:
        rny, rnx = rssi_grid.shape
        rssi_ref = np.zeros((ny, nx))
        for j in range(ny):
            for i in range(nx):
                ri = int(round(float(xs[i]) / fp.width * (rnx - 1)))
                rj = int(round(float(ys[j]) / fp.height * (rny - 1)))
                rssi_ref[j, i] = rssi_grid[
                    max(0, min(rny - 1, rj)), max(0, min(rnx - 1, ri))]
    else:
        rssi_ref = rssi_grid

    # 综合差覆盖评分
    rssi_score = np.clip((-rssi_ref + rssi_threshold) / 20.0, 0.0, 1.0)
    stall_score = np.clip(stall_grid / max(stall_threshold * 4, 0.20), 0.0, 1.0)
    badness = rssi_score * 0.5 + stall_score * 0.5

    existing = [(ap.x, ap.y) for ap in fp.aps]
    recs: list[dict] = []

    for k in range(n_recommend):
        b = badness.copy()
        for bx, by_ in existing + [(r["x"], r["y"]) for r in recs]:
            for j in range(ny):
                for i in range(nx):
                    if math.sqrt((float(xs[i]) - bx) ** 2 + (float(ys[j]) - by_) ** 2) < min_dist:
                        b[j, i] = 0.0

        if float(b.max()) < 0.02:
            break

        j_best, i_best = np.unravel_index(int(b.argmax()), b.shape)
        recs.append({
            "x": float(xs[i_best]),
            "y": float(ys[j_best]),
            "rssi": float(rssi_ref[j_best, i_best]),
            "stall_rate": float(stall_grid[j_best, i_best]),
            "score": float(badness[j_best, i_best]),
            "label": f"推荐AP{k + 1}",
        })

    return recs
