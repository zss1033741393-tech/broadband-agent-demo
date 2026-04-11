#!/usr/bin/env python3
"""FAE 平台 CEI 权重配置下发入口。

调用方式::

    python cei_threshold_config.py --weights ServiceQualityWeight:40,WiFiNetworkWeight:25,...
    python cei_threshold_config.py --weights ServiceQualityWeight:40 --config /path/to/config.ini

无 --weights 参数时使用默认权重（8 维度加和 100）。

部署要求：
- ``fae_poc/NCELogin.py`` 必须存在（用户本地部署）
- ``fae_poc/config.ini`` 必须存在（可通过 ``--config`` 显式指定）
详见 ``fae_poc/README.md``。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# ─── fae_poc 包注入 ────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FAE_POC_DIR = _PROJECT_ROOT / "fae_poc"
for _p in (str(_PROJECT_ROOT), str(_FAE_POC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fae_poc import DEFAULT_CONFIG_PATH, require_config  # noqa: E402

# ─── 默认权重 ────────────────────────────────────────────────────────
_DEFAULT_WEIGHTS: Dict[str, int] = {
    "ServiceQualityWeight": 30,
    "WiFiNetworkWeight": 20,
    "StabilityWeight": 15,
    "STAKPIWeight": 10,
    "GatewayKPIWeight": 10,
    "RateWeight": 5,
    "ODNWeight": 5,
    "OLTKPIWeight": 5,
}

_ALLOWED_KEYS = set(_DEFAULT_WEIGHTS.keys())


def _parse_weights(raw: str) -> Dict[str, int]:
    """解析 CSV 格式的权重字符串。

    Args:
        raw: 如 ``"ServiceQualityWeight:40,WiFiNetworkWeight:25"``

    Returns:
        合并后的完整权重字典（未传的维度保持默认值）

    Raises:
        ValueError: 非法的参数名或数值
    """
    weights = dict(_DEFAULT_WEIGHTS)
    if not raw or not raw.strip():
        return weights

    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"权重格式错误，缺少冒号分隔符: '{item}'，期望格式 'Name:Value'")
        key, val_str = item.split(":", 1)
        key = key.strip()
        val_str = val_str.strip()
        if key not in _ALLOWED_KEYS:
            raise ValueError(f"未知权重参数: '{key}'，允许的参数: {sorted(_ALLOWED_KEYS)}")
        try:
            val = int(val_str)
        except ValueError:
            raise ValueError(f"权重值必须为整数: '{key}:{val_str}'")
        if not (0 <= val <= 100):
            raise ValueError(f"权重值超出范围 0-100: '{key}:{val}'")
        weights[key] = val

    return weights


def _make_result(
    status: str,
    stage: str,
    weights: Optional[Dict[str, int]] = None,
    message: str = "",
    detail: Any = None,
) -> Dict[str, Any]:
    """构造标准化返回 JSON。"""
    result: Dict[str, Any] = {"status": status, "stage": stage}
    if message:
        result["message"] = message
    if weights is not None:
        result["weights"] = weights
    if detail is not None:
        result["detail"] = detail
    return result


def execute(weights_csv: str = "", config_path: Optional[str] = None) -> Dict[str, Any]:
    """执行 CEI 权重配置下发。

    Args:
        weights_csv: CSV 格式权重字符串，空字符串时使用默认权重
        config_path: config.ini 路径，None 时使用 fae_poc 默认路径

    Returns:
        结构化结果字典
    """
    # 1. 解析权重
    try:
        weights = _parse_weights(weights_csv)
    except ValueError as e:
        return _make_result("failed", "param_validation", message=str(e))

    # 2. 校验 config.ini
    try:
        resolved_config = require_config(Path(config_path) if config_path else None)
    except FileNotFoundError as e:
        return _make_result(
            "failed",
            "deployment_check",
            weights=weights,
            message=f"config.ini 未找到: {e}",
        )

    # 3. 校验 NCELogin
    try:
        from NCELogin import NCELogin  # bare 导入
    except ImportError as e:
        return _make_result(
            "failed",
            "deployment_check",
            weights=weights,
            message=f"NCELogin 未部署: {e}",
        )

    # 4. 登录 FAE 平台
    try:
        nce_login = NCELogin(config_file=str(resolved_config))
        nce_login.login(timeout=(5, 15))
    except Exception as e:
        return _make_result(
            "failed",
            "login",
            weights=weights,
            message=f"FAE 平台登录失败: {e}",
        )

    # 5. 下发权重配置
    try:
        # 构造 FAE config-threshold 请求体
        payload = {
            "thresholdConfig": [{"parameterName": k, "weight": v} for k, v in weights.items()]
        }
        response = nce_login.session.put(
            f"{nce_login.base_url}/api/v1/cei/config-threshold",
            json=payload,
            timeout=(5, 15),
        )
        response.raise_for_status()
        resp_data = response.json()
        return _make_result(
            "success",
            "config_threshold",
            weights=weights,
            message="CEI 权重配置下发成功",
            detail=resp_data,
        )
    except Exception as e:
        return _make_result(
            "failed",
            "config_threshold",
            weights=weights,
            message=f"CEI 权重配置下发失败: {e}",
        )


def main() -> None:
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="CEI 权重配置下发")
    parser.add_argument(
        "--weights",
        type=str,
        default="",
        help="8 维度权重 CSV，格式 Name1:V1,Name2:V2,...（省略时使用默认权重）",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(DEFAULT_CONFIG_PATH),
        help=f"config.ini 路径（默认: {DEFAULT_CONFIG_PATH}）",
    )
    args = parser.parse_args()
    result = execute(weights_csv=args.weights, config_path=args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
