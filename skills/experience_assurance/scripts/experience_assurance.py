#!/usr/bin/env python3
"""体验保障配置 Skill 入口 — 参数解析 + 接口调用 + 结果打包。

职责：
1. 解析 CLI 参数（--application-type / --application / --business-type）；
2. 在真实 FAE 环境下调用 NCELogin + ExperienceAssuranceClient 完成接口调用；
   在 demo/mock 环境下（FAE 依赖不可用时）返回符合接口协议的 mock 数据；
3. 将结果保存至 output_dir/experience_assurance_output.json（向后兼容）；
4. 向 stdout 输出 **单行** 结构化 JSON（供 event_adapter 解析为 SSE 事件）；
   其余进度日志一律写 stderr，不污染 stdout。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

# ─── 路径 ─────────────────────────────────────────────────────────────────────

_SCRIPT_DIR = Path(__file__).resolve().parent
_SKILL_DIR = _SCRIPT_DIR.parent
_PROJECT_ROOT = _SKILL_DIR.parents[1]      # broadband-agent/
_OUTPUT_DIR = _SKILL_DIR / "output_dir"

# ─── 常量 ─────────────────────────────────────────────────────────────────────

_VALID_APPLICATION_TYPES: set[str] = {
    "anchor-video",
    "real-time-game",
    "cloud-platform",
    "online-office",
}
_VALID_BUSINESS_TYPES: set[str] = {
    "experience-assurance",
    "speed-limit",
    "app-flow",
}

# 保障应用名称 → mock app_id（demo 阶段；接入真实应用目录后替换为运行时查询）
_APP_ID_MAP: dict[str, str] = {
    "TikTok":      "12345678-1234-1234-1234-tiktok000001",
    "Kwai":        "12345678-1234-1234-1234-kwai00000002",
    "抖音":        "12345678-1234-1234-1234-123456789001",
    "快手":        "12345678-1234-1234-1234-123456789002",
    "B站":         "12345678-1234-1234-1234-123456789003",
    "王者荣耀":    "12345678-1234-1234-1234-123456789004",
    "和平精英":    "12345678-1234-1234-1234-123456789005",
}
_APP_ID_FALLBACK = "12345678-1234-1234-1234-123456789000"

# demo mock 设备 UUID（无设备发现 Skill 时使用）
_MOCK_NE_ID     = "12345678-1234-1234-1234-123456789999"
_MOCK_ONU_RES_ID = "12345678-1234-1234-1234-123456789999"


# ─── 参数解析 ─────────────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> argparse.Namespace:
    """解析 CLI 参数。"""
    parser = argparse.ArgumentParser(description="体验保障配置接口调用工具")
    parser.add_argument(
        "--application-type",
        dest="application_type",
        default="anchor-video",
        choices=sorted(_VALID_APPLICATION_TYPES),
        help="应用类型（business-type=experience-assurance 时有效）",
    )
    parser.add_argument(
        "--application",
        dest="application",
        default="TikTok",
        help="保障应用名称（TikTok / Kwai / 抖音 / 快手 等）",
    )
    parser.add_argument(
        "--business-type",
        dest="business_type",
        default="experience-assurance",
        choices=sorted(_VALID_BUSINESS_TYPES),
        help="业务类型（experience-assurance / speed-limit / app-flow）",
    )
    parser.add_argument(
        "--config",
        default=str(_PROJECT_ROOT / "fae_poc" / "config.ini"),
        help="FAE 配置文件路径（含 NCELogin 认证信息）",
    )
    return parser.parse_args(argv)


# ─── Mock 数据构造 ─────────────────────────────────────────────────────────────

def _build_mock_result(
    application_type: str | None,
    application: str | None,
    business_type: str,
) -> dict[str, Any]:
    """生成符合 FAN 接口协议的 mock 结果数据。"""
    app_id = _APP_ID_MAP.get(application or "", _APP_ID_FALLBACK)
    service_type_map = {
        "experience-assurance": "assure",
        "speed-limit": "speed-limit",
        "app-flow": "app-flow",
    }
    return {
        "taskId": str(uuid.uuid4()),
        "neName": "200.30.33.63",
        "neIp": "200.30.33.63",
        "fsp": "0/3/2",
        "onuId": 5,
        "servicePortIndex": 0,
        "serviceName": "103/0_3_2/5/1/多业务VLAN模式/1",
        "configStatus": 0,
        "runningStatus": 1,
        "policyProfile": "defaultProfile",
        "limitProfile": "",
        "serviceType": service_type_map.get(business_type, business_type),
        "appCategory": application_type or "",
        "appId": app_id,
        "appName": application or "",
        "startTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "timeLimit": -1,
    }


# ─── 真实 FAE 调用（可选，FAE 依赖不可用时自动降级 mock） ────────────────────

def _call_fae(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """尝试调用真实 FAE 接口；失败返回 None（调用方降级 mock）。"""
    try:
        # 把 fae_poc 所在目录插入 path
        fae_root = str(_PROJECT_ROOT)
        if fae_root not in sys.path:
            sys.path.insert(0, fae_root)

        from NCELogin import NCELogin  # type: ignore
        from fae_poc.experience_assurance_client import (  # type: ignore
            ExperienceAssuranceClient,
            process_input_args,
        )

        nce_login = NCELogin(config_file=args.config)
        if not nce_login.is_token_expired(config_file=args.config):
            # token 有效
            client_kwargs = {
                "base_url": nce_login.base_url,
                "csrf_token": nce_login.csrf_token,
                "cookie": nce_login.cookie,
            }
        else:
            if not nce_login.get_cookie_and_token():
                print("[FAE] 登录失败，降级 mock", file=sys.stderr)
                return None
            client_kwargs = {"base_url": nce_login.base_url, "nce_login": nce_login}

        client = ExperienceAssuranceClient(**client_kwargs)

        (
            base_url, csrf_token, cookie,
            ne_id, service_port_index, policy_profile,
            onu_res_id, app_id,
        ) = process_input_args(args)

        client.create_assure_config_task(
            ne_id=ne_id,
            service_port_index=service_port_index,
            policy_profile=policy_profile,
            onu_res_id=onu_res_id,
            app_id=app_id,
        )
        result: dict[str, Any] = client.query_assure_config_task(
            ne_ip="200.30.33.63",
            fsp="0/3/2",
            onu_id="5",
            args=args,
        )
        return result

    except Exception as exc:
        print(f"[FAE] 接口调用异常，降级 mock: {exc}", file=sys.stderr)
        return None


# ─── 主入口 ──────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    """脚本入口。

    Args:
        argv: CLI 参数列表（None 时取 sys.argv[1:]）

    Returns:
        0=成功，1=失败
    """
    if argv is None:
        argv = sys.argv[1:]

    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        err = {
            "skill": "experience_assurance",
            "status": "error",
            "message": f"参数解析失败: exit code {exc.code}",
        }
        sys.stdout.write(json.dumps(err, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 1

    # business-type 不是 experience-assurance 时，application-type / application 无意义
    if args.business_type != "experience-assurance":
        eff_app_type = None
        eff_app = None
    else:
        eff_app_type = args.application_type
        eff_app = args.application

    print(f"[experience_assurance] business_type={args.business_type} "
          f"application_type={eff_app_type} application={eff_app}", file=sys.stderr)

    # 尝试真实调用，失败降级 mock
    result = _call_fae(args)
    is_mock = result is None
    if is_mock:
        result = _build_mock_result(eff_app_type, eff_app, args.business_type)
        print("[experience_assurance] 使用 mock 数据", file=sys.stderr)

    # 保存结果文件
    try:
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_file = _OUTPUT_DIR / "experience_assurance_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[experience_assurance] 结果已保存: {output_file}", file=sys.stderr)
    except Exception as exc:
        print(f"[experience_assurance] 保存文件失败: {exc}", file=sys.stderr)
        output_file = None  # 不阻断主流程

    # stdout 单行 JSON（event_adapter 解析来源）
    output: dict[str, Any] = {
        "skill": "experience_assurance",
        "status": "ok",
        "business_type": args.business_type,
        "application_type": eff_app_type,
        "application": eff_app,
        "is_mock": is_mock,
        "result": result,
        "output_file": str(output_file) if output_file else None,
    }
    sys.stdout.write(json.dumps(output, ensure_ascii=False) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
