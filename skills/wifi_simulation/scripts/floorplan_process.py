#!/usr/bin/env python3
"""
户型图处理脚本 (01_floorplan_process.py)

功能：
    输入户型图图片（2D），使用 YOLO+RFDETR 双模型进行墙体检测与分割，
    识别墙体线段，生成简化户型图和固定大小（400x400）的栅格地图。

集成：
    内置 floorplan_processor 深度学习处理能力，将墙体坐标 JSON 转换为栅格地图。

用法：
    python scripts/01_floorplan_process.py <input_image> [options]

示例：
    python scripts/01_floorplan_process.py data/floorplan.jpg
    python scripts/01_floorplan_process.py data/floorplan.jpg --output-dir output/ --grid-size 400

输出：
    - {output_dir}/grid_map.npy: 栅格地图 NumPy 数组（shape: 400 x 400）
    - {output_dir}/grid_info.json: 栅格地图元数据（scale, width, height）
    - {output_dir}/simplified_floorplan.png: 简化的户型图可视化
    - {output_dir}/walls.json: 原始墙体坐标数据
"""

from __future__ import annotations

import copy
import json
import math
import os
import sys
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple

import cv2
import numpy as np
import typer
from typing_extensions import Annotated

# ================= 常量定义 =================
DEFAULT_GRID_SIZE = 400
DEFAULT_SCALE = 0.05  # 0.05 m/px = 5cm/px, 400px = 20m (适合室内户型图)
DEFAULT_SMODEL_PATH = "models/65s.pt"
DEFAULT_DMODEL_PATH = "models/911checkpoint_best_ema.pth"
DEFAULT_CONF = 0.55
DEFAULT_DET_THRESHOLD = 0.3
DEFAULT_MERGE_THRESHOLD = 5
DEFAULT_EXTEND_LENGTH = 10
DEFAULT_DELETE_THRESHOLD = 20
DEFAULT_MONITOR_INTERVAL = 0.5

# 材质类型定义
MATERIAL_NAMES: Dict[int, str] = {
    0: "空旷",
    1: "砖墙",
    2: "门",
    3: "窗",
    4: "混凝土",
}

MATERIAL_COLORS: Dict[int, list] = {
    0: [255, 255, 255],
    1: [128, 128, 128],
    2: [139, 69, 19],
    3: [135, 206, 235],
    4: [64, 64, 64],
}

ATTENUATION_MAP: Dict[int, int] = {
    0: 0,
    1: 12,
    2: 3,
    3: 5,
    4: 25,
}


# ================= 栅格地图数据结构 =================


@dataclass
class GridMap:
    """栅格地图数据结构。"""

    grid: np.ndarray
    scale: float
    width: int
    height: int

    def get_attenuation(self, x: int, y: int) -> int:
        if 0 <= x < self.width and 0 <= y < self.height:
            return ATTENUATION_MAP.get(int(self.grid[y, x]), 0)
        return 0

    def is_obstacle(self, x: int, y: int) -> bool:
        if 0 <= x < self.width and 0 <= y < self.height:
            return self.grid[y, x] > 0
        return False

    def pixel_to_meter(self, px: int, py: int) -> Tuple[float, float]:
        return (px * self.scale, py * self.scale)

    def meter_to_pixel(self, mx: float, my: float) -> Tuple[int, int]:
        return (int(mx / self.scale), int(my / self.scale))


# ================= 几何数据结构定义 =================


@dataclass
class Vector2(np.lib.mixins.NDArrayOperatorsMixin):
    """二维向量类"""

    x: float = field(default=0.0)
    y: float = field(default=0.0)

    def __array__(self) -> np.ndarray:
        return np.array((self.x, self.y))

    def __array_ufunc__(self, ufunc, method, *inputs, **kwargs) -> "Vector2":
        from numbers import Number

        if method == "__call__":
            scalars = []
            objects = []
            for i in inputs:
                if isinstance(i, Number):
                    scalars.append(i)
                elif isinstance(i, self.__class__):
                    objects.append(np.array((i.x, i.y)))
                elif isinstance(i, (list, np.ndarray)):
                    objects.append(i)
                else:
                    return NotImplementedError("not support the other type")
            return self.__class__(*ufunc(*objects, *scalars, **kwargs))
        return NotImplementedError("now only support __call__!")

    def __getitem__(self, item) -> float:
        if item == 0:
            return self.x
        if item == 1:
            return self.y
        raise IndexError("Vector2 index out of range")

    def __len__(self):
        return 2

    def __eq__(self, other) -> bool:
        if isinstance(other, Vector2):
            return self.x == other.x and self.y == other.y
        return self.x == other[0] and self.y == other[1]

    def __hash__(self):
        return hash((self.x, self.y))

    @property
    def length(self) -> float:
        return math.hypot(self.x, self.y)

    @property
    def normalize(self) -> "Vector2":
        num = self.length
        if num > 9.999999747378752e-06:
            v = self / num
        else:
            v = Vector2(0, 0)
        return Vector2(*v)

    def copy(self) -> "Vector2":
        return Vector2(self.x, self.y)

    def round(self) -> "Vector2":
        return Vector2(round(self.x), round(self.y))

    def __add__(self, other):
        if isinstance(other, Vector2):
            return Vector2(self.x + other.x, self.y + other.y)
        return Vector2(self.x + other, self.y + other)

    def __sub__(self, other):
        if isinstance(other, Vector2):
            return Vector2(self.x - other.x, self.y - other.y)
        return Vector2(self.x - other, self.y - other)

    def __mul__(self, other):
        if isinstance(other, (int, float)):
            return Vector2(self.x * other, self.y * other)
        return NotImplemented

    def __truediv__(self, other):
        if isinstance(other, (int, float)):
            return Vector2(self.x / other, self.y / other)
        return NotImplemented


class IntersectionType(Enum):
    empty = 0
    point = 1
    line = 2


@dataclass
class Intersection:
    type: IntersectionType = field(default=IntersectionType.empty)
    point: Vector2 = field(default_factory=Vector2)
    line0: Optional["Line"] = None
    line1: Optional["Line"] = None


class Line:
    """线段类"""

    def __init__(self, p0, p1):
        if isinstance(p0, Vector2):
            self.p0 = p0
        elif isinstance(p0, np.ndarray):
            self.p0 = Vector2(*p0)
        else:
            raise TypeError("p0 must be Vector2 or np.ndarray")

        if isinstance(p1, Vector2):
            self.p1 = p1
        elif isinstance(p1, np.ndarray):
            self.p1 = Vector2(*p1)
        else:
            raise TypeError("p1 must be Vector2 or np.ndarray")

    def __repr__(self):
        return f"Line({self.p0}, {self.p1})"

    @property
    def direction(self) -> Vector2:
        return self.p1 - self.p0

    @property
    def length(self) -> float:
        return (self.p1 - self.p0).length

    @property
    def normalize(self) -> Vector2:
        return (self.p1 - self.p0).normalize

    @property
    def xy(self):
        return np.array((self.p0, self.p1))

    @staticmethod
    def point_to_line_distance(point: Vector2, line: "Line") -> float:
        px, py = point.x, point.y
        x1, y1, x2, y2 = line.p0.x, line.p0.y, line.p1.x, line.p1.y
        line_magnitude = math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        if line_magnitude < 0.00000001:
            return 9999
        u = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / (line_magnitude**2)
        if u < 0 or u > 1:
            ix = math.sqrt((px - x1) ** 2 + (py - y1) ** 2)
            iy = math.sqrt((px - x2) ** 2 + (py - y2) ** 2)
            return min(ix, iy)
        ix = x1 + u * (x2 - x1)
        iy = y1 + u * (y2 - y1)
        return math.sqrt((px - ix) ** 2 + (py - iy) ** 2)

    @staticmethod
    def point_project(line: "Line", point: Vector2) -> Vector2:
        normal = line.normalize
        a, b = normal.x, normal.y
        x1, y1 = line.p0.x, line.p0.y
        x0, y0 = point.x, point.y
        t = -(a * (x1 - x0) + b * (y1 - y0)) / (a**2 + b**2)
        return Vector2(int(a * t + x1), int(b * t + y1))

    @staticmethod
    def intersect(origin: "Line", other: "Line") -> Intersection:
        try:
            from shapely.geometry import LineString

            line1 = LineString([origin.p0, origin.p1])
            line2 = LineString([other.p0, other.p1])
            int_pt = line1.intersection(line2)
            if int_pt.is_empty:
                return Intersection(IntersectionType.empty)
            return Intersection(IntersectionType.point, Vector2(int_pt.x, int_pt.y))
        except ImportError:
            return Intersection(IntersectionType.empty)

    def point_is_inside_line(self, point: Vector2) -> bool:
        return min(self.p0.x, self.p1.x) <= point.x <= max(self.p0.x, self.p1.x) and min(
            self.p0.y, self.p1.y
        ) <= point.y <= max(self.p0.y, self.p1.y)

    def copy(self) -> "Line":
        return Line(self.p0.copy(), self.p1.copy())


@dataclass
class PlanData:
    """户型数据结构类"""

    classes: int = 0
    bbox: Optional[np.ndarray] = None
    score: float = 0.0
    obox: Optional[np.ndarray] = None

    def __post_init__(self):
        if self.bbox is not None:
            self.bbox = self.bbox.reshape(2, 2).astype(np.int32)


@dataclass
class ProcessConfig:
    """图像处理配置类"""

    smodel_path: str
    dmodel_path: str
    output_dir: str = "result"
    infer_conf: float = DEFAULT_CONF
    det_threshold: float = DEFAULT_DET_THRESHOLD
    merge_threshold: int = DEFAULT_MERGE_THRESHOLD
    extend_length: int = DEFAULT_EXTEND_LENGTH
    delete_threshold: int = DEFAULT_DELETE_THRESHOLD


class PerformanceMonitor:
    def __init__(self, config: ProcessConfig):
        try:
            import psutil

            self.process = psutil.Process(os.getpid())
        except ImportError:
            self.process = None
        self.interval = config.monitor_interval
        self.running = False
        self.cpu_samples = []
        self.mem_samples = []

    def start(self):
        if self.process:
            self.running = True
            threading.Thread(target=self._sample, daemon=True).start()

    def stop(self):
        self.running = False

    def _sample(self):
        while self.running and self.process:
            self.cpu_samples.append(self.process.cpu_percent(interval=None))
            self.mem_samples.append(self.process.memory_info().rss / 1024 / 1024)
            time.sleep(self.interval)


class ModelManager:
    """模型加载与推理管理类"""

    def __init__(self, config: ProcessConfig):
        self.config = config
        self.smodel = None
        self.dmodel = None

    def load_models(self):
        from rfdetr import RFDETRBase
        from ultralytics import YOLO

        self.smodel = YOLO(self.config.smodel_path, task="segment")
        self.dmodel = RFDETRBase(pretrain_weights=self.config.dmodel_path, num_classes=3)
        return self

    def infer(self, image):
        start = time.time()
        sresults = self.smodel.predict(source=image, conf=self.config.infer_conf)
        dresults = self.dmodel.predict(image, threshold=self.config.det_threshold)
        return sresults, dresults, time.time() - start


def preprocess_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    std = np.std(gray)
    if std > 30:
        enhanced = gray
    else:
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = cv2.filter2D(
            clahe.apply(gray), -1, np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        )
    return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)


def transfer_rf_detr(detections) -> list[PlanData]:
    plan_datas = []
    for det in detections if isinstance(detections, (list, tuple)) else [detections]:
        boxes = np.ceil(det.xyxy).astype(int)
        classes = det.class_id.astype(int)
        for idx, box in enumerate(boxes):
            plan_datas.append(PlanData(classes=int(classes[idx]), bbox=box.reshape(2, 2)))
    return plan_datas


def transfer(results) -> list[PlanData]:
    plan_datas = []
    for r in results:
        boxes = r.boxes.xyxy.cpu().numpy().astype(int)
        classes = r.boxes.cls.cpu().numpy().astype(int)
        for idx, box in enumerate(boxes):
            plan_datas.append(PlanData(classes=int(classes[idx]), bbox=box.reshape(2, 2)))
    return plan_datas


def get_line_bbox(data) -> Optional[Line]:
    if data.bbox is None or data.bbox.shape != (2, 2):
        return None
    min_pt = Vector2(*data.bbox[0])
    max_pt = Vector2(*data.bbox[1])
    center = ((min_pt + max_pt) / 2).round()
    width = max_pt.x - min_pt.x
    height = max_pt.y - min_pt.y
    if width > height and width / height > 1.5:
        return Line(
            Vector2(center.x - width / 2, center.y),
            Vector2(center.x + width / 2, center.y),
        )
    elif height > width and height / width > 1.5:
        return Line(
            Vector2(center.x, center.y - height / 2),
            Vector2(center.x, center.y + height / 2),
        )
    return None


def merge_lines(lines: list[Line], dt: int = 5) -> list[Line]:
    lines_sorted = sorted(copy.deepcopy(lines), key=lambda x: x.length, reverse=True)
    for origin in lines_sorted:
        direction_matched = [
            o
            for o in lines_sorted
            if o != origin and origin.normalize in (o.normalize, Line(o.p1, o.p0).normalize)
        ]
        distance_matched = [
            o
            for o in direction_matched
            if Line.point_to_line_distance(o.p0, origin) <= dt
            or Line.point_to_line_distance(o.p1, origin) <= dt
        ]
        if distance_matched:
            target = distance_matched[0]
            points = sorted(
                [
                    Line.point_project(origin, target.p0),
                    Line.point_project(origin, target.p1),
                    origin.p0,
                    origin.p1,
                ],
                key=lambda x: x.length,
            )
            origin.p0, origin.p1 = points[0], points[3]
            lines_sorted.remove(target)
            return merge_lines(lines_sorted, dt)
    return lines_sorted


def extend_lines(lines: list[Line], threshold: int = 50) -> list[Line]:
    lines_new = sorted(copy.deepcopy(lines), key=lambda x: x.length)
    for origin in lines_new:
        normalized = origin.normalize * threshold
        left = Line(origin.p0 - normalized, origin.p1)
        right = Line(origin.p0, origin.p1 + normalized)
        for other in lines_new:
            if other == origin:
                continue
            for line in [left, right]:
                intersect = Line.intersect(line, other)
                if intersect.type == IntersectionType.point and not Line.point_is_inside_line(
                    origin, intersect.point
                ):
                    points = sorted([intersect.point, origin.p0, origin.p1], key=lambda x: x.length)
                    origin.p0, origin.p1 = points[0].round(), points[2].round()
                    return extend_lines(lines_new, threshold)
    return lines_new


def split_lines(lines: list[Line]) -> list[Line]:
    lines_new = copy.deepcopy(lines)
    out_lines = []
    for origin in lines_new:
        points = [
            intersect.point
            for other in lines_new
            if other != origin
            and (intersect := Line.intersect(origin, other)).type == IntersectionType.point
            and Line.point_is_inside_line(origin, intersect.point)
        ]
        points.extend([origin.p0, origin.p1])
        points = sorted(points, key=lambda x: x.length)
        for i in range(len(points) - 1):
            out_lines.append(Line(points[i].round(), points[i + 1].round()))
    return out_lines


def delete_lines(lines: list[Line], threshold: int = 50) -> list[Line]:
    lines_new = copy.deepcopy(lines)
    out_lines = []
    for line in lines_new:
        if line.p0 == line.p1:
            continue
        left_conn = [o for o in lines_new if o != line and line.p0 in (o.p0, o.p1)]
        right_conn = [o for o in lines_new if o != line and line.p1 in (o.p0, o.p1)]
        if left_conn and right_conn:
            out_lines.append(line)
        elif (left_conn or right_conn) and line.length >= threshold:
            out_lines.append(line)
    return out_lines


def generate_coordinate(walls: list[Line]) -> dict:
    return {
        "walls": [
            {
                "x": {"start": int(w.xy[0][0]), "end": int(w.xy[1][0])},
                "y": {"start": int(w.xy[0][1]), "end": int(w.xy[1][1])},
            }
            for w in walls
        ]
    }


class ImageProcessor:
    def __init__(self, config: ProcessConfig, model_manager: ModelManager):
        self.config = config
        self.model_manager = model_manager

    def process_single_image(self, image_path: Path) -> list[Line]:
        image = cv2.imdecode(np.fromfile(str(image_path), dtype=np.uint8), cv2.IMREAD_COLOR)
        image = preprocess_image(image)
        sresults, dresults, _ = self.model_manager.infer(image)

        dwalls = [get_line_bbox(pd) for pd in transfer_rf_detr(dresults) if get_line_bbox(pd)]
        swalls = [get_line_bbox(pd) for pd in transfer(sresults) if get_line_bbox(pd)]

        walls = [w for w in dwalls + swalls if w]
        walls = merge_lines(walls, self.config.merge_threshold)
        walls = extend_lines(walls, self.config.extend_length)
        walls = split_lines(walls)
        walls = delete_lines(walls, self.config.delete_threshold)

        json_path = Path(self.config.output_dir) / "json" / f"{image_path.stem}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(generate_coordinate(walls), f)

        return walls


def walls_json_to_grid(walls_json: dict, shape: tuple, grid_size: int = 400) -> np.ndarray:
    h, w = shape[:2]
    grid = np.zeros((grid_size, grid_size), dtype=np.uint8)
    for wall in walls_json.get("walls", []):
        x0 = min(int(wall["x"]["start"] / w * grid_size), grid_size - 1)
        x1 = min(int(wall["x"]["end"] / w * grid_size), grid_size - 1)
        y0 = min(int(wall["y"]["start"] / h * grid_size), grid_size - 1)
        y1 = min(int(wall["y"]["end"] / h * grid_size), grid_size - 1)
        cv2.line(grid, (x0, y0), (x1, y1), 1, 3)
    return grid


def create_mock_grid_with_materials(
    image_path: Path, grid_size: int = 400
) -> Tuple[np.ndarray, float]:
    """创建带有不同材质分布的模拟栅格地图

    改进：给墙体赋予适当厚度，填充墙体区域，基于合理比例分配材质
    """
    image = cv2.imread(str(image_path))
    if image is None:
        return np.zeros((grid_size, grid_size), dtype=np.uint8), DEFAULT_SCALE

    h, w = image.shape[:2]
    scale = DEFAULT_SCALE

    # 转换为灰度图
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # 边缘检测
    edges = cv2.Canny(gray, 50, 150)

    # 形态学处理 - 使用更大的kernel给墙体赋予适当厚度
    # 迭代次数增加使墙体更粗壮，模拟实际墙体宽度
    thick_kernel = np.ones((5, 5), np.uint8)
    dilated = cv2.dilate(edges, thick_kernel, iterations=3)

    # 使用闭运算填充墙体内部间隙
    closed = cv2.morphologyEx(dilated, cv2.MORPH_CLOSE, thick_kernel, iterations=2)

    # 缩放到目标尺寸
    grid = cv2.resize(closed, (grid_size, grid_size), interpolation=cv2.INTER_AREA)

    # 初始化材质栅格
    material_grid = np.zeros((grid_size, grid_size), dtype=np.uint8)

    # 墙体区域标记为砖墙 (1)
    material_grid[grid > 0] = 1

    # ========== 改进：基于合理比例分配材质 ==========
    # 使用图像的局部特征来区分不同材质
    resized_gray = cv2.resize(gray, (grid_size, grid_size))

    # 第一步：先扩大墙体区域（给墙体适当厚度）
    wall_expand_kernel = np.ones((7, 7), np.uint8)
    wall_expanded = cv2.dilate(
        (material_grid == 1).astype(np.uint8), wall_expand_kernel, iterations=2
    )

    # 更新墙体区域（仅扩展空旷区域）
    material_grid[(wall_expanded > 0) & (material_grid == 0)] = 1

    # 第二步：检测门区域 - 门通常是墙体上的较暗缺口
    door_kernel = np.ones((3, 3), np.uint8)
    wall_border = cv2.dilate((material_grid == 1).astype(np.uint8), door_kernel, iterations=1)

    # 门：在墙体边缘的暗色小区域
    _, dark_mask = cv2.threshold(resized_gray, 100, 255, cv2.THRESH_BINARY_INV)
    potential_doors = dark_mask & wall_border
    door_mask = potential_doors.astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(door_mask, connectivity=8)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        # 门的大小范围：15-300平方像素
        if 15 < area < 300:
            material_grid[labels == i] = 2

    # 第三步：检测窗区域 - 窗通常是墙体上较亮的窄条
    # 窗：在墙体上且较亮的小区域
    _, bright_mask = cv2.threshold(resized_gray, 180, 255, cv2.THRESH_BINARY)
    # 窗应该在墙体内（不是墙体外扩区域）
    wall_core = cv2.erode((material_grid == 1).astype(np.uint8), door_kernel, iterations=1)
    potential_windows = bright_mask & wall_core
    window_mask = potential_windows.astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(window_mask, connectivity=8)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        # 窗的大小范围：10-200平方像素（比门小
        if 10 < area < 200:
            # 检查是否为细长形状（窗通常是细长的）
            bbox = cv2.boundingRect((labels == i).astype(np.uint8))
            aspect_ratio = max(bbox[2], bbox[3]) / max(min(bbox[2], bbox[3]), 1)
            if aspect_ratio > 1.5:  # 长宽比大于1.5认为是窗
                material_grid[labels == i] = 3

    # 第四步：标记混凝土 (4) - 外墙和结构性墙体
    # 计算到图像边缘的距离（使用向量化计算替代循环）
    y_coords, x_coords = np.ogrid[:grid_size, :grid_size]
    dist_from_edge = np.minimum(
        np.minimum(y_coords, grid_size - 1 - y_coords),
        np.minimum(x_coords, grid_size - 1 - x_coords),
    )

    # 最外层（距离边缘<10%边长）的墙体标记为混凝土
    edge_threshold = grid_size * 0.10
    outer_concrete_mask = (material_grid == 1) & (dist_from_edge < edge_threshold)

    # 记录外墙位置用于后续恢复
    outer_concrete_coords = np.argwhere(outer_concrete_mask)

    # 第五步：如果材质分布不合理，进行调整（仅调整非外墙区域）
    # 统计当前材质分布（不含混凝土）
    unique, counts = np.unique(material_grid, return_counts=True)
    current_dist = dict(zip(unique, counts))
    total_wall_pixels = sum(current_dist.get(i, 0) for i in [1, 2, 3, 4])
    total_pixels = grid_size * grid_size
    wall_ratio = total_wall_pixels / total_pixels

    # 如果墙体比例过低（<8%），增加墙体厚度
    if wall_ratio < 0.08:
        interior_mask = (material_grid == 1) & ~outer_concrete_mask
        additional_wall = cv2.dilate(
            interior_mask.astype(np.uint8),
            np.ones((3, 3), np.uint8),
            iterations=1,
        )
        material_grid[(additional_wall > 0) & (material_grid == 0)] = 1

    # 如果墙体比例过高（>30%），缩小墙体（但不侵蚀外墙）
    unique, counts = np.unique(material_grid, return_counts=True)
    current_dist = dict(zip(unique, counts))
    total_wall_pixels = sum(current_dist.get(i, 0) for i in [1, 2, 3, 4])
    wall_ratio = total_wall_pixels / total_pixels

    if wall_ratio > 0.30:
        interior_mask = (material_grid == 1) & ~outer_concrete_mask
        eroded = cv2.erode(
            interior_mask.astype(np.uint8),
            np.ones((3, 3), np.uint8),
            iterations=1,
        )
        # 只保留门和窗（非外墙区域的）
        material_grid[
            (eroded == 0) & (material_grid != 2) & (material_grid != 3) & ~outer_concrete_mask
        ] = 0
        material_grid[(material_grid == 1) & (eroded == 0) & ~outer_concrete_mask] = 0

    # 重新标记外墙为混凝土（使用保存的坐标）
    for y, x in outer_concrete_coords:
        if material_grid[y, x] == 1:  # 只标记仍然是墙体的
            material_grid[y, x] = 4

    # 第六步：再次检测门窗（因为墙体可能变了）
    _, dark_mask = cv2.threshold(resized_gray, 100, 255, cv2.THRESH_BINARY_INV)
    wall_border = cv2.dilate((material_grid == 1).astype(np.uint8), door_kernel, iterations=1)
    potential_doors = dark_mask & wall_border
    door_mask = potential_doors.astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(door_mask, connectivity=8)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if 15 < area < 300:
            material_grid[labels == i] = 2

    _, bright_mask = cv2.threshold(resized_gray, 180, 255, cv2.THRESH_BINARY)
    wall_core = cv2.erode((material_grid == 1).astype(np.uint8), door_kernel, iterations=1)
    potential_windows = bright_mask & wall_core
    window_mask = potential_windows.astype(np.uint8)
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(window_mask, connectivity=8)
    for i in range(1, num_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if 10 < area < 200:
            bbox = cv2.boundingRect((labels == i).astype(np.uint8))
            aspect_ratio = max(bbox[2], bbox[3]) / max(min(bbox[2], bbox[3]), 1)
            if aspect_ratio > 1.5:
                material_grid[labels == i] = 3

    return material_grid, scale


def visualize_grid(grid: np.ndarray, scale: float, output_path: Path) -> None:
    """将栅格地图可视化为彩色图像，支持中文显示"""
    from PIL import Image, ImageDraw, ImageFont

    h, w = grid.shape

    # 创建基础可视化图像
    vis = np.zeros((h, w, 3), dtype=np.uint8)
    for material_id, color in MATERIAL_COLORS.items():
        mask = grid == material_id
        vis[mask] = color

    # 添加网格线
    grid_interval = max(1, w // 16)
    for i in range(0, w, grid_interval):
        cv2.line(vis, (i, 0), (i, h), (200, 200, 200), 1)
    for j in range(0, h, grid_interval):
        cv2.line(vis, (0, j), (w, j), (200, 200, 200), 1)

    # 转换为PIL图像
    vis_pil = Image.fromarray(vis)

    # 创建图例区域
    legend_height = 140
    result_height = h + legend_height
    result = Image.new("RGB", (w, result_height), (240, 240, 240))
    result.paste(vis_pil, (0, 0))

    draw = ImageDraw.Draw(result)

    # 尝试加载系统中文字体
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",  # macOS
        "/System/Library/Fonts/STHeiti Light.ttc",  # macOS备选
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # Linux
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # Linux备选
        "C:/Windows/Fonts/simhei.ttf",  # Windows
        "C:/Windows/Fonts/msyh.ttc",  # Windows备选
    ]

    font = None
    font_small = None
    for font_path in font_paths:
        try:
            font = ImageFont.truetype(font_path, 16)
            font_small = ImageFont.truetype(font_path, 14)
            break
        except:
            continue

    if font is None:
        font = ImageFont.load_default()
        font_small = font

    # 绘制标题
    title = f"栅格地图 ({w}×{h}) | 比例尺: {scale:.3f}米/像素 | 实际: {w * scale:.1f}米 × {h * scale:.1f}米"
    draw.text((10, h + 10), title, fill=(50, 50, 50), font=font)

    # 绘制材质图例
    y_pos = h + 40
    x_pos = 10
    box_size = 15
    spacing = 100

    for material_id, name in MATERIAL_NAMES.items():
        color_rgb = MATERIAL_COLORS[material_id]
        # 绘制颜色方块
        draw.rectangle(
            [x_pos, y_pos, x_pos + box_size, y_pos + box_size],
            fill=tuple(color_rgb),
            outline=(100, 100, 100),
        )
        # 绘制材质名称
        draw.text((x_pos + box_size + 5, y_pos), name, fill=(50, 50, 50), font=font_small)
        x_pos += spacing
        # 换行
        if x_pos > w - 80:
            x_pos = 10
            y_pos += 25

    # 保存图像
    result.save(str(output_path))
    print(f"  ✓ 栅格可视化已保存: {output_path}", file=sys.stderr)


def grid_to_walls_json(grid: np.ndarray, original_shape: tuple) -> dict:
    """从栅格地图提取墙体坐标（用于轮廓检测模式）"""
    h, w = original_shape[:2]
    grid_h, grid_w = grid.shape

    # 查找所有墙体像素
    walls = []
    visited = np.zeros_like(grid, dtype=bool)

    for y in range(grid_h):
        for x in range(grid_w):
            if grid[y, x] > 0 and not visited[y, x]:
                # 查找连续的水平线段
                x_end = x
                while x_end < grid_w and grid[y, x_end] > 0 and not visited[y, x_end]:
                    visited[y, x_end] = True
                    x_end += 1

                if x_end > x + 2:  # 至少3个像素才视为墙体
                    walls.append(
                        {
                            "x": {
                                "start": int(x / grid_w * w),
                                "end": int((x_end - 1) / grid_w * w),
                            },
                            "y": {
                                "start": int(y / grid_h * h),
                                "end": int(y / grid_h * h),
                            },
                        }
                    )

    return {"walls": walls}


def process_floorplan(
    input_image: Path,
    output_dir: Path,
    grid_size: int = DEFAULT_GRID_SIZE,
    use_dl: bool = True,
) -> GridMap:
    print("=" * 60)
    print("户型图处理脚本")
    print("=" * 60)
    print(f"输入图片: {input_image}")
    print(f"目标栅格大小: {grid_size}x{grid_size}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)
    image = cv2.imread(str(input_image))
    if image is None:
        print(f"错误: 无法读取图片: {input_image}")
        sys.exit(1)

    h, w = image.shape[:2]
    print("[1/4] 加载户型图...")
    print(f"  原始尺寸: {w}x{h}")

    walls_json = None
    source = "contour_detection"

    if use_dl:
        print("[2/4] 使用深度学习模型处理...")
        models_dir = Path(__file__).parent.parent / "models"
        smodel, dmodel = (
            models_dir / "65s.pt",
            models_dir / "911checkpoint_best_ema.pth",
        )
        if smodel.exists() and dmodel.exists():
            try:
                config = ProcessConfig(
                    smodel_path=str(smodel),
                    dmodel_path=str(dmodel),
                    output_dir=str(output_dir / "temp"),
                )
                processor = ImageProcessor(config, ModelManager(config).load_models())
                processor.process_single_image(input_image)
                json_path = output_dir / "temp" / "json" / f"{input_image.stem}.json"
                if json_path.exists():
                    with open(json_path, encoding="utf-8") as f:
                        walls_json = json.load(f)
                    source = "deep_learning"
                    print("  ✓ 深度学习模型处理完成")
            except Exception as e:
                print(f"  警告: 深度学习处理失败: {e}")
                print("  将使用轮廓检测备用方案...")
        else:
            print("  警告: 模型文件不存在，使用轮廓检测备用方案...")
    else:
        print("[2/4] 使用轮廓检测处理...")

    print("[3/4] 生成栅格地图...")

    if walls_json:
        grid = walls_json_to_grid(walls_json, (h, w), grid_size)
        computed_scale = DEFAULT_SCALE
    else:
        print("  使用轮廓检测...")
        grid, computed_scale = create_mock_grid_with_materials(input_image, grid_size)
        walls_json = grid_to_walls_json(grid, (h, w))

    # 保存 walls.json
    walls_path = output_dir / "walls.json"
    with open(walls_path, "w", encoding="utf-8") as f:
        json.dump(walls_json, f, indent=2, ensure_ascii=False)
    print(f"  ✓ 墙体坐标已保存: {walls_path}")

    scale = computed_scale

    grid_map = GridMap(grid=grid, scale=scale, width=grid_size, height=grid_size)

    print(f"  栅格尺寸: {grid_map.width}x{grid_map.height}")
    print(f"  比例尺: {grid_map.scale:.4f} m/px")
    print(
        f"  实际面积: {grid_map.width * grid_map.scale:.1f}m x {grid_map.height * grid_map.scale:.1f}m"
    )

    unique, counts = np.unique(grid_map.grid, return_counts=True)
    print("  材质分布:")
    for val, count in zip(unique, counts):
        percentage = count / grid_map.grid.size * 100
        print(f"    - {MATERIAL_NAMES.get(int(val), '未知')}: {count} ({percentage:.1f}%)")

    print()
    print("[4/4] 保存输出文件...")

    grid_path = output_dir / "grid_map.npy"
    np.save(grid_path, grid_map.grid)
    print(f"  ✓ 栅格地图: {grid_path}")

    grid_info = {
        "width": int(grid_map.width),
        "height": int(grid_map.height),
        "scale": float(grid_map.scale),
        "scale_unit": "meters_per_pixel",
        "real_width_m": float(grid_map.width * grid_map.scale),
        "real_height_m": float(grid_map.height * grid_map.scale),
        "material_map": {str(k): v for k, v in MATERIAL_NAMES.items()},
        "source": source,
    }
    info_path = output_dir / "grid_info.json"
    with open(info_path, "w", encoding="utf-8") as f:
        json.dump(grid_info, f, indent=2, ensure_ascii=False)
    print(f"  ✓ 栅格信息: {info_path}")

    # 生成可视化图像
    vis_path = output_dir / "simplified_floorplan.png"
    visualize_grid(grid_map.grid, grid_map.scale, vis_path)
    print(f"  ✓ 简化户型图: {vis_path}")

    print()
    print("=" * 60)
    print(f"处理完成！输出目录: {output_dir}")
    print("=" * 60)

    return grid_map


app = typer.Typer()


@app.command()
def process(
    input_image: Annotated[Path, typer.Argument()],
    output_dir: Annotated[Path, typer.Option("-o", "--output-dir")] = Path("output/floorplan"),
    grid_size: Annotated[int, typer.Option("-g", "--grid-size")] = DEFAULT_GRID_SIZE,
    no_dl: Annotated[bool, typer.Option("--no-dl")] = False,
):
    process_floorplan(input_image, output_dir, grid_size, not no_dl)


if __name__ == "__main__":
    app()
