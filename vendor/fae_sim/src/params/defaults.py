"""默认参数集。"""

from .schema import SimParams

# 使用 SimParams 全部默认值，代表典型家庭场景：
# WiFi6 路由器 + GPON，中等信号条件，8Mbps 高清 RTMP 推流
DEFAULT_PARAMS = SimParams()
