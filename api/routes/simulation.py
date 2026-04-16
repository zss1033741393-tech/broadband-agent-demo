"""仿真 API 路由 — 直接调用 FAE_demo 仿真引擎，通过 SSE 批次流推送结果。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from src.engine import SimulationEngine
from src.faults import FaultConfig, FAULT_CATALOG
from src.params.schema import SimParams

from api.sse import format_sse

router = APIRouter(prefix="/simulation", tags=["simulation"])
_log = logger.bind(channel="simulation")

# 时间序列中需要转为 float 的数值键白名单；其余键（如 primary_stall_type 为字符串）跳过
_TS_KEYS = {
    "step", "effective_up_throughput", "buffer_watermark",
    "stall_active", "tcp_retrans_rate", "up_jitter",
    "frame_gen_flag", "frame_drop_flag",
}

# ──────────────────────────────────────────────────────────────────────────────
# 仿真引擎单例
# ──────────────────────────────────────────────────────────────────────────────
_engine = SimulationEngine()

FAULT_NAME_TO_ID: dict[str, int] = {
    "频繁WiFi漫游": 1, "WiFi干扰严重": 2, "WiFi覆盖弱": 3,
    "上行带宽不足": 4, "PON口拥塞": 5, "多STA竞争": 6, "PON光纤中断": 7,
}

_DEFAULT_PARAMS: dict = dict(
    wifi_channel=36, wifi_bandwidth=80, wifi_rssi=-50.0,
    wifi_noise_floor=-90.0, wifi_interference_ratio=45.0, sta_count=15,
    wifi_standard="wifi6", sta_spatial_streams=2, wifi_retry_rate=5.0,
    wifi_up_retry_rate=5.0, wifi_multipath_fading=0.2,
    wifi_mu_mimo_enabled=True, wifi_gi=800, wifi_code_rate="5/6",
    wifi_up_tcp_retrans_rate=2.0, wifi_up_latency=10.0, wifi_up_jitter=5.0,
    pon_uplink_bw=50.0, pon_downlink_bw=1000.0, pon_rx_power=-15.0,
    pon_optical_attenuation=10.0, pon_split_ratio=64, pon_up_load_ratio=50.0,
    pon_down_load_ratio=40.0, pon_dba_cycle=2.0, pon_burst_collision=0.01,
    pon_es=5.0, user_priority_weight=1.0, pon_tx_power=-10.0,
    pon_bip_error_rate=1e-7, pon_fec_pre_error_rate=1e-4,
    pon_fec_post_error_rate=1e-9, pon_up_tcp_retrans_rate=2.0,
    pon_up_latency=20.0, pon_up_jitter=10.0,
    rtmp_bitrate=8.0, rtmp_buffer_ms=200, video_frame_interval=33.0,
    video_frame_avg_size=16384, rtmp_chunk_size=4096,
    tcp_retrans_threshold=5.0, rtmp_heartbeat_timeout=3000,
    sim_duration=200, random_seed=42,
)


def _make_default_params() -> SimParams:
    d = dict(_DEFAULT_PARAMS)
    seed = d.pop("random_seed")
    return SimParams(**d, random_seed=seed)


# ──────────────────────────────────────────────────────────────────────────────
# 会话状态
# ──────────────────────────────────────────────────────────────────────────────
@dataclass
class SimSession:
    params: SimParams
    sim_prev: dict | None = None
    step_offset: int = 0
    current_fault_id: int = 0
    current_fault_name: str = ""
    segments: list[str] = field(default_factory=list)
    summaries: list[dict] = field(default_factory=list)


_sim_sessions: dict[str, SimSession] = {}


def _summary_to_dict(summary) -> dict:
    return {
        "stallRate": round(float(summary.rtmp_stall_rate), 2),
        "avgThroughput": round(float(summary.avg_effective_throughput), 2),
        "tcpBlockRatio": round(float(summary.tcp_block_ratio), 2),
        "bandwidthMeetRate": round(float(summary.bandwidth_meet_rate), 2),
    }


async def _stream_segment(
    conv_id: str,
    seg_type: str,
    run_params: SimParams,
    fault_config: FaultConfig | None = None,
    extra_event_data: dict | None = None,
) -> AsyncGenerator[str, None]:
    """运行一段仿真并以 SSE 批次流推送结果。"""
    session = _sim_sessions[conv_id]
    loop = asyncio.get_running_loop()
    try:
        # Run synchronous simulation in a thread executor to avoid blocking the event loop
        summary, ts, final_prev = await loop.run_in_executor(
            None,
            lambda: _engine.simulate(
                run_params,
                collect_timeseries=True,
                fault_config=fault_config,
                initial_prev=session.sim_prev,
                step_offset=session.step_offset,
            ),
        )
    except Exception as exc:
        _log.exception(f"仿真引擎异常 conv_id={conv_id} seg_type={seg_type}")
        yield format_sse("sim_error", {"message": str(exc)})
        return

    session.sim_prev = final_prev
    session.step_offset += run_params.total_steps
    session.segments.append(seg_type)
    session.summaries.append(_summary_to_dict(summary))
    _log.info(f"仿真段完成 conv_id={conv_id} seg_type={seg_type} "
              f"stall_rate={summary.rtmp_stall_rate:.2f}%")

    total = len(ts["step"])
    batch_size = max(1, total // 200)
    for i in range(0, total, batch_size):
        chunk: dict = {}
        for k, vals in ts.items():
            if k not in _TS_KEYS:
                continue
            chunk[k] = [float(v) for v in list(vals)[i:i + batch_size]]
        yield format_sse("sim_batch", {
            "batchIndex": i // batch_size,
            "segType": seg_type,
            "data": chunk,
        })
        await asyncio.sleep(0.05)

    seg_end_data: dict = {
        "segType": seg_type,
        "summary": session.summaries[-1],
    }
    if extra_event_data:
        seg_end_data.update(extra_event_data)
    yield format_sse("sim_segment_end", seg_end_data)
    yield format_sse("sim_done", {})


# ──────────────────────────────────────────────────────────────────────────────
# Request bodies
# ──────────────────────────────────────────────────────────────────────────────
class StartRequest(BaseModel):
    conv_id: str


class InjectFaultRequest(BaseModel):
    conv_id: str
    fault_name: str


class RemediateRequest(BaseModel):
    conv_id: str


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/start")
async def start_simulation(body: StartRequest):
    """初始化会话，运行基线段，SSE 流式推送批次数据。"""
    params = _make_default_params()
    _sim_sessions[body.conv_id] = SimSession(params=params)
    _log.info(f"仿真启动 conv_id={body.conv_id}")

    async def generate() -> AsyncGenerator[str, None]:
        async for chunk in _stream_segment(body.conv_id, "baseline", params):
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/inject-fault")
async def inject_fault(body: InjectFaultRequest):
    """注入故障段，随机注入模式 (count=30, max_duration=30)。"""
    if body.conv_id not in _sim_sessions:
        raise HTTPException(status_code=400, detail="仿真会话不存在，请先发送 '仿真：启动'")

    fault_id = FAULT_NAME_TO_ID.get(body.fault_name)
    if fault_id is None:
        raise HTTPException(status_code=400, detail=f"未知故障名称: {body.fault_name}")

    session = _sim_sessions[body.conv_id]
    session.current_fault_id = fault_id
    session.current_fault_name = body.fault_name

    fault_config = FaultConfig(
        enabled_faults=[fault_id],
        fault_inject_mode="random",
        random_fault_count=30,
        random_fault_max_duration=30,
        fault_recover_flag=False,
    )
    _log.info(f"故障注入 conv_id={body.conv_id} fault={body.fault_name}(id={fault_id})")

    async def generate() -> AsyncGenerator[str, None]:
        async for chunk in _stream_segment(body.conv_id, "fault", session.params, fault_config):
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.post("/remediate")
async def remediate(body: RemediateRequest):
    """执行故障自愈：应用绑定措施，运行恢复段。"""
    if body.conv_id not in _sim_sessions:
        raise HTTPException(status_code=400, detail="仿真会话不存在")

    session = _sim_sessions[body.conv_id]
    if session.current_fault_id == 0:
        raise HTTPException(status_code=400, detail="无活跃故障，无需自愈")

    fault_info = FAULT_CATALOG[session.current_fault_id]
    bound_measures: list[str] = fault_info["bound_measures"]

    recovery_params = session.params.copy()
    for measure_name in bound_measures:
        m = _engine.registry.get(measure_name)
        if m:
            recovery_params = m.apply(recovery_params)

    extra = {
        "faultName": session.current_fault_name,
        "measures": bound_measures,
    }
    _log.info(f"故障自愈 conv_id={body.conv_id} measures={bound_measures}")

    async def generate() -> AsyncGenerator[str, None]:
        async for chunk in _stream_segment(body.conv_id, "recovery", recovery_params,
                                           extra_event_data=extra):
            yield chunk

    return StreamingResponse(generate(), media_type="text/event-stream", headers=_SSE_HEADERS)
