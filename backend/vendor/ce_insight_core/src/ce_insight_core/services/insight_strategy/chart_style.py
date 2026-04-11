"""
图表配置工具：马卡龙色系 + 统一风格。
所有洞察函数的 _chart_configs 使用此模块构建。
"""

# 马卡龙色系
BLUE = "#7eb8da"  # 天蓝
RED = "#f2918c"  # 珊瑚粉
GREEN = "#8fd4b0"  # 薄荷绿
ORANGE = "#f5c378"  # 杏黄
PURPLE = "#b8a9e0"  # 薰衣草紫
CYAN = "#7ecdc0"  # 青瓷绿
PINK = "#e8a0bf"  # 樱花粉
GRAY = "#e8e8e8"
DARK_GRAY = "#b0b0b0"

# 多系列调色板（马卡龙）
PALETTE = [
    "#7eb8da",  # 天蓝
    "#f2918c",  # 珊瑚粉
    "#8fd4b0",  # 薄荷绿
    "#f5c378",  # 杏黄
    "#b8a9e0",  # 薰衣草紫
    "#7ecdc0",  # 青瓷绿
    "#e8a0bf",  # 樱花粉
    "#a3d9e8",  # 浅湖蓝
    "#f0b88a",  # 奶茶橙
    "#c5e0a5",  # 嫩芽绿
]

# 强调色（用于标注最值/异常/变点）
HIGHLIGHT_RED = "#e76f6f"  # 柔和红
HIGHLIGHT_GREEN = "#6bc78e"  # 柔和绿


def truncate_label(s: str, max_len: int = 10) -> str:
    """截断超长标签"""
    s = str(s)
    return s if len(s) <= max_len else s[:max_len] + "..."


def truncate_labels(labels: list, max_len: int = 10) -> list:
    return [truncate_label(s, max_len) for s in labels]


def base_grid() -> dict:
    return {"left": "10%", "right": "6%", "bottom": "14%", "top": "16%", "containLabel": False}


def base_title(text: str) -> dict:
    return {
        "text": text,
        "left": "center",
        "textStyle": {"fontSize": 13, "color": "#4a4a4a", "fontWeight": 600},
    }


def rotated_axis_label(rotate: int = 30) -> dict:
    return {"fontSize": 10, "rotate": rotate}


def base_tooltip(trigger: str = "axis") -> dict:
    return {"trigger": trigger, "confine": True, "textStyle": {"fontSize": 11}}
