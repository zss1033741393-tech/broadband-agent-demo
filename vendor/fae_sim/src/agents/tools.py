"""体验保障 Agent 的工具函数实现。

这些是 **纯 Python 函数**，通过 get_bridge() 访问当前 Streamlit 会话。
CrewAI 的 @tool 装饰器在 assurance_agent.py 里把它们包装成 Crew 工具，
这样测试层可以不依赖 crewai 直接调用。

写操作的语义是"排队"：只更新 session_state 中的 user_params / agent_pending_actions，
真正的仿真由 app.py 在 rerun 后调用 _run_segment() 顺序执行。
"""

from __future__ import annotations

import json
from typing import Any

from .session_bridge import get_bridge


# ══════════════════════════════════════════════════════════════════════
#  小工具
# ══════════════════════════════════════════════════════════════════════

_WIFI_KEYS = [
    "wifi_channel", "wifi_bandwidth", "wifi_rssi", "wifi_noise_floor",
    "wifi_interference_ratio", "sta_count", "wifi_standard",
    "sta_spatial_streams", "wifi_retry_rate", "wifi_up_retry_rate",
    "wifi_multipath_fading", "wifi_mu_mimo_enabled", "wifi_gi",
    "wifi_code_rate", "wifi_up_tcp_retrans_rate", "wifi_up_latency",
    "wifi_up_jitter",
]
_PON_KEYS = [
    "pon_uplink_bw", "pon_downlink_bw", "pon_rx_power",
    "pon_optical_attenuation", "pon_split_ratio", "pon_up_load_ratio",
    "pon_down_load_ratio", "pon_dba_cycle", "pon_burst_collision",
    "pon_es", "user_priority_weight", "pon_tx_power",
    "pon_bip_error_rate", "pon_fec_pre_error_rate", "pon_fec_post_error_rate",
    "pon_up_tcp_retrans_rate", "pon_up_latency", "pon_up_jitter",
]
_RTMP_KEYS = [
    "rtmp_bitrate", "rtmp_buffer_ms", "video_frame_interval",
    "video_frame_avg_size", "rtmp_chunk_size", "tcp_retrans_threshold",
    "rtmp_heartbeat_timeout", "sim_duration",
]


def _build_sim_params(up: dict):
    """把 user_params dict 转换为 SimParams（供 diagnose / experience_index 使用）。"""
    from ..params.schema import SimParams
    allowed = {f: up[f] for f in up if f != "random_seed"}
    return SimParams(**allowed, random_seed=up.get("random_seed"))


def _fmt_num(v, digits=2) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v)


# ══════════════════════════════════════════════════════════════════════
#  读类工具
# ══════════════════════════════════════════════════════════════════════


def get_current_params() -> str:
    """返回当前仿真参数的 JSON（分 WiFi / PON / RTMP 三段）。"""
    bridge = get_bridge()
    up = bridge.user_params()
    payload = {
        "WiFi": {k: up.get(k) for k in _WIFI_KEYS if k in up},
        "PON": {k: up.get(k) for k in _PON_KEYS if k in up},
        "RTMP": {k: up.get(k) for k in _RTMP_KEYS if k in up},
        "random_seed": up.get("random_seed"),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def get_latest_summary() -> str:
    """返回最新一段仿真的核心 KPI（卡顿率、瓶颈、吞吐、TCP 阻塞、时延/抖动、异常参数等）。"""
    bridge = get_bridge()
    s = bridge.latest_summary()
    if s is None:
        return "当前没有仿真结果。请先运行 reset_simulation 或等待基线仿真完成。"

    segments = bridge.all_segments()
    seg_type = segments[-1][1] if segments else "unknown"
    seg_label = {"baseline": "基线", "fault": "故障注入", "recovery": "措施恢复"}.get(seg_type, seg_type)

    lines = [
        f"当前段类型: {seg_label} (第 {len(segments)} 段)",
        f"RTMP 卡顿率: {_fmt_num(s.rtmp_stall_rate)}%",
        f"卡顿事件数: {s.stall_count}",
        f"平均卡顿时长: {_fmt_num(s.avg_stall_duration_ms, 0)} ms",
        f"瓶颈: {s.bottleneck or '无'}",
        f"平均上行有效吞吐: {_fmt_num(s.avg_effective_throughput)} Mbps",
        f"带宽达标率: {_fmt_num(s.bandwidth_meet_rate)}%",
        f"TCP 阻塞比例: {_fmt_num(s.tcp_block_ratio)}%",
        f"平均 TCP 重传率: {_fmt_num(s.avg_tcp_retrans_rate, 3)}",
        f"断连次数: {s.reconnect_count}",
        f"平均上行时延: {_fmt_num(s.avg_up_latency)} ms",
        f"平均上行抖动: {_fmt_num(s.avg_up_jitter)} ms",
        f"缓冲区耗尽占比: {_fmt_num(s.buffer_empty_ratio)}%",
    ]

    dist = s.stall_type_distribution or {}
    if dist:
        type_names = {
            "buffer_empty": "缓冲区耗尽", "frame_timeout": "帧超时",
            "tcp_block": "TCP 阻塞", "reconnect": "断连重推",
        }
        parts = [f"{type_names.get(k, k)}={v}" for k, v in dist.items() if v > 0]
        if parts:
            lines.append("卡顿类型分布: " + ", ".join(parts))

    ap = s.abnormal_params or []
    if ap:
        parts = [f"{p.get('param')}={_fmt_num(p.get('avg_value'))}" for p in ap[:5]]
        lines.append("异常参数: " + "; ".join(parts))

    return "\n".join(lines)


def get_experience_index_breakdown() -> str:
    """返回最新窗口的 8 维体验指数（总分 + 各维度 + 最低维度）。"""
    from ..models.experience_index import compute_experience_index

    bridge = get_bridge()
    ts = bridge.latest_timeseries()
    if ts is None:
        return "当前没有时序数据可用于计算体验指数。"

    up = bridge.user_params()
    try:
        params = _build_sim_params(up)
    except Exception as e:
        return f"构建参数失败: {e}"

    windows = compute_experience_index(ts, params, window_size=100, slide_step=10)
    if not windows:
        return "体验指数窗口为空（仿真段可能过短）。"

    latest = windows[-1]
    dim_lines = [f"- {k}: {_fmt_num(v, 1)}" for k, v in latest.dimension_scores.items()]
    min_dim = min(latest.dimension_scores.items(), key=lambda kv: kv[1])
    label = "优秀" if latest.total_score >= 80 else ("良好" if latest.total_score >= 60 else "较差")
    return (
        f"最新窗口体验指数总分: **{_fmt_num(latest.total_score, 0)}** / 100 ({label})\n"
        f"最低维度: {min_dim[0]} = {_fmt_num(min_dim[1], 1)}\n"
        f"8 维度分数:\n" + "\n".join(dim_lines)
    )


def get_diagnosis() -> str:
    """对最新段仿真结果运行故障诊断，返回定界 + 前 3 个故障候选 + 推荐措施。"""
    from ..models.fault_diagnosis import diagnose

    bridge = get_bridge()
    s = bridge.latest_summary()
    if s is None:
        return "当前没有仿真结果可供诊断。"

    ts = bridge.latest_timeseries()
    up = bridge.user_params()
    try:
        params = _build_sim_params(up)
    except Exception as e:
        return f"构建参数失败: {e}"

    result = diagnose(s, params, timeseries=ts)
    if not result.has_issue:
        return f"[无显著问题] {result.summary_text}"

    lines = [
        f"定界: {result.domain} 域",
        f"摘要: {result.summary_text}",
        "故障候选:",
    ]
    for i, fc in enumerate(result.fault_candidates, 1):
        lines.append(
            f"  {i}. [{fc.severity}, 置信度{fc.confidence}] "
            f"故障{fc.fault_id} {fc.fault_name}"
        )
        lines.append(f"     证据: {'; '.join(fc.evidence)}")
        lines.append(f"     绑定措施: {', '.join(fc.measures)}")
    return "\n".join(lines)


def list_faults() -> str:
    """列出全部 7 个可注入故障（ID / 名称 / 严重度 / 绑定措施）。"""
    from ..faults.fault_config import FAULT_CATALOG
    lines = ["可注入的故障目录："]
    for fid, info in FAULT_CATALOG.items():
        measures = ", ".join(info["bound_measures"])
        lines.append(f"  {fid}. {info['name']} [{info['severity']}] → 绑定措施: {measures}")
    return "\n".join(lines)


def list_measures() -> str:
    """列出当前引擎注册的全部闭环措施（name / description）。"""
    bridge = get_bridge()
    engine = bridge.engine
    measures = engine.registry.list_all()
    lines = ["可用的闭环措施："]
    for m in measures:
        lines.append(f"  - {m.name}: {m.description}")
    return "\n".join(lines)


def compare_segments(metric: str = "rtmp_stall_rate") -> str:
    """对比各分段仿真的指定指标，用于修复前/后效果评估。

    可用 metric: rtmp_stall_rate, stall_count, avg_effective_throughput,
    bandwidth_meet_rate, tcp_block_ratio, avg_up_latency, avg_up_jitter,
    avg_stall_duration_ms, reconnect_count, buffer_empty_ratio。
    """
    bridge = get_bridge()
    summaries = bridge.all_summaries()
    segments = bridge.all_segments()
    if not summaries:
        return "暂无仿真结果。"

    seg_label_map = {"baseline": "基线", "fault": "故障注入", "recovery": "措施恢复"}
    lines = [f"分段对比（指标: {metric}）:"]
    for i, s in enumerate(summaries):
        seg_type = segments[i][1] if i < len(segments) else "?"
        label = seg_label_map.get(seg_type, seg_type)
        val = getattr(s, metric, None)
        if val is None:
            lines.append(f"  [{i+1}] {label}: 字段 {metric} 不存在")
        else:
            lines.append(f"  [{i+1}] {label}: {_fmt_num(val, 2)}")

    # 若存在故障+恢复，额外计算改善百分比
    if len(summaries) >= 2:
        vals = [getattr(s, metric, None) for s in summaries]
        if all(v is not None for v in vals):
            first, last = float(vals[0]), float(vals[-1])
            if first != 0:
                delta_pct = (last - first) / abs(first) * 100
                lines.append(f"  首段 → 末段变化: {_fmt_num(delta_pct, 1)}%")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════
#  写类工具
# ══════════════════════════════════════════════════════════════════════


def update_sim_params(updates_json: str) -> str:
    """修改一个或多个仿真参数并排队重跑基线仿真。

    updates_json: JSON 字符串，例如 '{"wifi_rssi": -70, "sta_count": 30}'
    仅允许修改已知 SimParams 字段；会先校验一次，校验失败则不排队。
    """
    from ..params.schema import SimParams

    bridge = get_bridge()
    try:
        updates = json.loads(updates_json) if isinstance(updates_json, str) else updates_json
    except (json.JSONDecodeError, TypeError) as e:
        return f"错误: updates_json 必须是合法 JSON 字符串，解析失败: {e}"
    if not isinstance(updates, dict) or not updates:
        return "错误: updates 必须是非空 JSON 对象。"

    # 字段白名单
    allowed_keys = set(_WIFI_KEYS + _PON_KEYS + _RTMP_KEYS) | {"random_seed"}
    unknown = [k for k in updates if k not in allowed_keys]
    if unknown:
        return f"错误: 未知参数字段: {unknown}"

    # 试构造一份新的 params 做校验
    up = dict(bridge.user_params())
    up.update(updates)
    try:
        probe_kwargs = {k: v for k, v in up.items() if k != "random_seed"}
        probe = SimParams(**probe_kwargs, random_seed=up.get("random_seed"))
        errors = probe.validate()
        if errors:
            return "参数校验失败:\n  - " + "\n  - ".join(errors)
    except Exception as e:
        return f"参数构造失败: {e}"

    # 写入并排队
    bridge.update_user_params(updates)
    bridge.queue_action({"kind": "params"})
    summary_items = ", ".join(f"{k}={v}" for k, v in updates.items())
    return f"已更新参数并排队重跑基线仿真: {summary_items}"


def inject_fault(fault_ids_csv: str, mode: str = "fixed") -> str:
    """注入一个或多个故障场景，排队故障段仿真。

    fault_ids_csv: 逗号分隔的故障 ID，例如 "2" 或 "2,5"（范围 1~7）。
    mode: "fixed"（固定全程注入）或 "random"（随机片段注入）。
    """
    from ..faults import FaultConfig, FAULT_CATALOG

    bridge = get_bridge()
    try:
        fault_ids = [int(x.strip()) for x in str(fault_ids_csv).split(",") if x.strip()]
    except ValueError:
        return f"错误: fault_ids_csv 必须是逗号分隔的整数，当前: {fault_ids_csv}"
    if not fault_ids:
        return "错误: 至少需要一个 fault_id。"
    invalid = [fid for fid in fault_ids if fid not in FAULT_CATALOG]
    if invalid:
        return f"错误: 无效的故障 ID: {invalid}（合法范围 1~7）"
    if mode not in ("fixed", "random"):
        return f"错误: mode 必须是 'fixed' 或 'random'，当前: {mode}"

    if mode == "fixed":
        fc = FaultConfig(
            enabled_faults=list(fault_ids),
            fault_inject_mode="fixed",
            fault_start_step=1,
            fault_duration_step=-1,
            fault_recover_flag=False,
        )
    else:
        fc = FaultConfig(
            enabled_faults=list(fault_ids),
            fault_inject_mode="random",
            random_fault_count=5,
            random_fault_max_duration=2000,
            fault_recover_flag=False,
        )

    bridge.queue_action({"kind": "fault", "fault_config": fc})
    names = ", ".join(f"{fid}.{FAULT_CATALOG[fid]['name']}" for fid in fault_ids)
    return f"已排队注入故障段 ({mode} 模式): {names}"


def apply_measures(measure_names_csv: str) -> str:
    """应用一个或多个闭环措施，排队恢复段仿真。

    measure_names_csv: 逗号分隔的措施英文 ID，例如 "wifi_channel_opt" 或 "wifi_channel_opt,pon_expansion"。
    """
    bridge = get_bridge()
    engine = bridge.engine
    measure_names = [n.strip() for n in str(measure_names_csv).split(",") if n.strip()]
    if not measure_names:
        return "错误: 至少需要一个 measure name。"
    all_names = {m.name for m in engine.registry.list_all()}
    unknown = [n for n in measure_names if n not in all_names]
    if unknown:
        return f"错误: 未知措施: {unknown}。可用措施请调用 list_measures()。"

    bridge.queue_action({"kind": "recovery", "measures": list(measure_names)})
    return f"已排队应用措施 (恢复段): {', '.join(measure_names)}"


def reset_simulation() -> str:
    """清空所有分段，重新从基线开始仿真。"""
    bridge = get_bridge()
    bridge.queue_action({"kind": "reset"})
    return "已排队重置仿真。本次回复后将从头运行基线段。"


def auto_fix_current_faults() -> str:
    """自动修复：基于当前最新段运行故障诊断，取置信度最高的候选的绑定措施排队恢复段。

    执行后调用 compare_segments() 会给出修复前/后对比（需等 Streamlit 重跑后再读）。
    """
    from ..models.fault_diagnosis import diagnose

    bridge = get_bridge()
    s = bridge.latest_summary()
    if s is None:
        return "当前没有仿真结果，无法自动修复。请先运行基线 / 故障段。"

    ts = bridge.latest_timeseries()
    up = bridge.user_params()
    try:
        params = _build_sim_params(up)
    except Exception as e:
        return f"参数构造失败: {e}"

    result = diagnose(s, params, timeseries=ts)
    if not result.has_issue or not result.fault_candidates:
        return (
            "诊断未发现显著问题，或没有匹配的故障模式，无需自动修复。"
            f" 诊断摘要: {result.summary_text}"
        )

    top = result.fault_candidates[0]
    measures = top.measures or []
    if not measures:
        return f"故障 {top.fault_name} 没有绑定修复措施，无法自动修复。"

    bridge.queue_action({"kind": "recovery", "measures": list(measures)})
    baseline_rate = _fmt_num(s.rtmp_stall_rate, 2)
    return (
        f"诊断结果: {top.fault_name}（{top.severity}, 置信度{top.confidence}）\n"
        f"证据: {'; '.join(top.evidence)}\n"
        f"已排队应用修复措施: {', '.join(measures)}\n"
        f"当前段卡顿率: {baseline_rate}%（修复段完成后可调用 compare_segments('rtmp_stall_rate') 查看前/后对比）"
    )


def get_wifi_coverage_summary() -> str:
    """获取 WiFi 环境仿真的覆盖质量摘要（户型、AP 位置、终端信号强度、覆盖评价）。

    读取 session_state 中的 WiFi 环境数据并计算各终端的信号强度。
    """
    bridge = get_bridge()
    ss = bridge.ss
    if "wifi_fp_base" not in ss:
        return "WiFi 环境尚未初始化。请先切换到 WiFi 环境 Tab 选择户型。"

    try:
        from ..models.home_environment import FloorPlan, Room, AP, STA, rssi_at_sta
    except ImportError:
        return "WiFi 环境模块未安装。"

    fp_base = ss["wifi_fp_base"]
    aps_data = ss.get("wifi_aps", [])
    stas_data = ss.get("wifi_stas", [])
    rooms_data = ss.get("wifi_rooms", [])

    # 重建 FloorPlan
    fp = FloorPlan(name=fp_base.name, width=fp_base.width, height=fp_base.height)
    fp.rooms = [Room(r["name"], r["x"], r["y"], r["w"], r["h"]) for r in rooms_data]
    fp.walls = list(fp_base.walls)
    fp.aps = [AP(a["x"], a["y"], a.get("tx_power", 20.0), a.get("label", "AP"))
              for a in aps_data]
    fp.stas = [STA(s["x"], s["y"], s.get("label", "STA")) for s in stas_data]

    lines = [
        f"户型: {fp.name} ({fp.width}m x {fp.height}m)",
        f"房间: {', '.join(r['name'] for r in rooms_data)}",
        f"AP 数量: {len(fp.aps)}",
    ]
    for i, ap in enumerate(fp.aps):
        lines.append(f"  AP{i+1}: ({ap.x:.1f}, {ap.y:.1f}), 发射功率 {ap.tx_power_dbm:.0f}dBm")

    lines.append(f"终端数量: {len(fp.stas)}")
    all_rssi = []
    for i, sta in enumerate(fp.stas):
        rssi = rssi_at_sta(fp, sta)
        all_rssi.append(rssi)
        quality = "优" if rssi > -50 else ("良" if rssi > -65 else ("中" if rssi > -75 else "差"))
        lines.append(f"  {sta.label}: ({sta.x:.1f}, {sta.y:.1f}), RSSI={rssi:.1f}dBm ({quality})")

    if all_rssi:
        avg = sum(all_rssi) / len(all_rssi)
        worst = min(all_rssi)
        overall = "覆盖良好" if worst > -65 else ("存在弱覆盖区域" if worst > -75 else "覆盖较差，建议增加AP或调整位置")
        lines.append(f"\n总体评价: {overall}")
        lines.append(f"平均 RSSI: {avg:.1f}dBm, 最差: {worst:.1f}dBm")

    return "\n".join(lines)


def switch_to_wifi_tab() -> str:
    """切换到 WiFi 环境仿真 Tab 页面（户型图 + 信号强度热力图）。

    当用户要求执行 WiFi 环境仿真、查看户型图、查看信号热力图、
    或调整 AP/终端位置时，调用此工具跳转到 WiFi 环境 Tab。
    """
    bridge = get_bridge()
    bridge.queue_action({"kind": "switch_tab", "tab": "wifi"})
    return "已排队切换到 WiFi 环境仿真 Tab。页面将自动跳转到户型图和信号强度仿真界面。"


# ══════════════════════════════════════════════════════════════════════
#  工具清单（供 assurance_agent.py 批量注册）
# ══════════════════════════════════════════════════════════════════════

READ_TOOLS = [
    get_current_params,
    get_latest_summary,
    get_experience_index_breakdown,
    get_diagnosis,
    list_faults,
    list_measures,
    compare_segments,
    get_wifi_coverage_summary,
]

WRITE_TOOLS = [
    update_sim_params,
    inject_fault,
    apply_measures,
    reset_simulation,
    auto_fix_current_faults,
    switch_to_wifi_tab,
]

ALL_TOOLS = READ_TOOLS + WRITE_TOOLS
