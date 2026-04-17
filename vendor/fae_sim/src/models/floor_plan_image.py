"""户型图图片识别模块。

从上传的户型图图片中自动识别墙体结构，生成 FloorPlan 模型。
"""

from __future__ import annotations

import cv2
import numpy as np

from .home_environment import FloorPlan, Wall, Room


def detect_walls_from_image(
    image_bytes: bytes,
    real_width: float = 12.0,
    real_height: float = 10.0,
    min_wall_length_m: float = 1.0,
    merge_distance_px: int = 15,
) -> FloorPlan:
    """从户型图图片中检测墙体，生成 FloorPlan。

    Args:
        image_bytes: 图片二进制数据。
        real_width: 实际宽度 (米)。
        real_height: 实际高度 (米)。
        min_wall_length_m: 最小墙体长度 (米)，短于此的线段忽略。
        merge_distance_px: 合并距离 (像素)，近距平行线合并为一条墙。
    """
    # 解码图片
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    h, w = img.shape[:2]

    # 缩放因子
    sx = real_width / w
    sy = real_height / h
    min_length_px = min_wall_length_m / max(sx, sy)

    # 预处理
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)

    # 自适应二值化（适应不同图片亮度）
    binary = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2,
    )

    # 形态学操作：膨胀连接断线，腐蚀去除噪点
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    binary = cv2.dilate(binary, kernel, iterations=1)
    binary = cv2.erode(binary, kernel, iterations=1)

    # Canny 边缘检测
    edges = cv2.Canny(binary, 50, 150, apertureSize=3)

    # 概率霍夫线变换
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=50,
        minLineLength=int(min_length_px),
        maxLineGap=20,
    )

    if lines is None:
        return FloorPlan(name="上传户型", width=real_width, height=real_height)

    # 提取线段并转换为实际坐标
    raw_segments: list[tuple[float, float, float, float]] = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        # 像素 → 米（y 轴翻转：图片坐标系上→下，户型坐标系下→上）
        mx1 = x1 * sx
        my1 = real_height - y1 * sy
        mx2 = x2 * sx
        my2 = real_height - y2 * sy
        raw_segments.append((mx1, my1, mx2, my2))

    # 对齐：接近水平/垂直的线段校正为严格水平/垂直
    aligned = _align_segments(raw_segments, angle_threshold=10.0)

    # 合并近距离平行线段
    merged = _merge_close_segments(aligned, merge_dist=merge_distance_px * max(sx, sy))

    # 构建墙体
    walls: list[Wall] = []
    for seg in merged:
        x1, y1, x2, y2 = seg
        length = np.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)
        # 根据长度推断墙类型：长墙=外墙(高衰减)，短墙=隔墙(低衰减)
        attenuation = 10.0 if length > max(real_width, real_height) * 0.4 else 5.0
        walls.append(Wall(
            round(x1, 2), round(y1, 2),
            round(x2, 2), round(y2, 2),
            attenuation,
        ))

    fp = FloorPlan(
        name="上传户型",
        width=real_width,
        height=real_height,
        walls=walls,
    )

    # 尝试从墙体围合区域推断房间
    fp.rooms = _infer_rooms(fp)

    return fp


def _align_segments(
    segments: list[tuple[float, float, float, float]],
    angle_threshold: float = 10.0,
) -> list[tuple[float, float, float, float]]:
    """将接近水平/垂直的线段校正为严格水平/垂直。"""
    result = []
    for x1, y1, x2, y2 in segments:
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        angle = np.degrees(np.arctan2(dy, dx))

        if angle < angle_threshold:
            # 接近水平 → 取 y 均值
            ym = (y1 + y2) / 2
            result.append((x1, ym, x2, ym))
        elif angle > (90 - angle_threshold):
            # 接近垂直 → 取 x 均值
            xm = (x1 + x2) / 2
            result.append((xm, y1, xm, y2))
        else:
            result.append((x1, y1, x2, y2))
    return result


def _merge_close_segments(
    segments: list[tuple[float, float, float, float]],
    merge_dist: float = 0.3,
) -> list[tuple[float, float, float, float]]:
    """合并近距平行线段。"""
    if not segments:
        return []

    used = [False] * len(segments)
    merged = []

    for i in range(len(segments)):
        if used[i]:
            continue
        group = [segments[i]]
        used[i] = True

        for j in range(i + 1, len(segments)):
            if used[j]:
                continue
            if _segments_parallel_and_close(segments[i], segments[j], merge_dist):
                group.append(segments[j])
                used[j] = True

        # 合并组内线段为一条
        all_pts = []
        for s in group:
            all_pts.extend([(s[0], s[1]), (s[2], s[3])])

        x1, y1, x2, y2 = group[0]
        is_horizontal = abs(y2 - y1) < abs(x2 - x1)

        if is_horizontal:
            ym = np.mean([p[1] for p in all_pts])
            xmin = min(p[0] for p in all_pts)
            xmax = max(p[0] for p in all_pts)
            merged.append((xmin, ym, xmax, ym))
        else:
            xm = np.mean([p[0] for p in all_pts])
            ymin = min(p[1] for p in all_pts)
            ymax = max(p[1] for p in all_pts)
            merged.append((xm, ymin, xm, ymax))

    return merged


def _segments_parallel_and_close(
    s1: tuple[float, float, float, float],
    s2: tuple[float, float, float, float],
    dist: float,
) -> bool:
    """判断两条线段是否平行且距离小于 dist。"""
    dx1, dy1 = s1[2] - s1[0], s1[3] - s1[1]
    dx2, dy2 = s2[2] - s2[0], s2[3] - s2[1]

    # 检查平行（叉积接近 0）
    cross = abs(dx1 * dy2 - dy1 * dx2)
    len1 = np.sqrt(dx1 ** 2 + dy1 ** 2)
    len2 = np.sqrt(dx2 ** 2 + dy2 ** 2)
    if len1 == 0 or len2 == 0:
        return False
    if cross / (len1 * len2) > 0.15:
        return False

    # 检查距离（中点间距）
    cx1, cy1 = (s1[0] + s1[2]) / 2, (s1[1] + s1[3]) / 2
    cx2, cy2 = (s2[0] + s2[2]) / 2, (s2[1] + s2[3]) / 2
    d = np.sqrt((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2)
    return d < dist * 3


def _infer_rooms(fp: FloorPlan) -> list[Room]:
    """从墙体围合尝试推断房间（简化版：按象限划分）。"""
    if not fp.walls:
        return [Room("全屋", 0, 0, fp.width, fp.height)]

    # 简化方案：将空间按主要墙体分割
    h_walls = [(w.y1, w) for w in fp.walls if abs(w.y2 - w.y1) < 0.1]
    v_walls = [(w.x1, w) for w in fp.walls if abs(w.x2 - w.x1) < 0.1]

    # 取 y 分界线
    y_cuts = sorted(set([0.0, fp.height] + [round(yw, 1) for yw, _ in h_walls]))
    x_cuts = sorted(set([0.0, fp.width] + [round(xw, 1) for xw, _ in v_walls]))

    # 过滤太小的区域
    rooms = []
    idx = 1
    for i in range(len(y_cuts) - 1):
        for j in range(len(x_cuts) - 1):
            x0, x1 = x_cuts[j], x_cuts[j + 1]
            y0, y1 = y_cuts[i], y_cuts[i + 1]
            w, h = x1 - x0, y1 - y0
            if w > 1.0 and h > 1.0:
                rooms.append(Room(f"区域{idx}", round(x0, 1), round(y0, 1), round(w, 1), round(h, 1)))
                idx += 1

    return rooms if rooms else [Room("全屋", 0, 0, fp.width, fp.height)]
