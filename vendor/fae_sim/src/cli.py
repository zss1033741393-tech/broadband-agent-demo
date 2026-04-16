"""CLI 入口 — RTMP推流仿真命令行。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .params.schema import SimParams
from .params.defaults import DEFAULT_PARAMS
from .engine import SimulationEngine

app = typer.Typer(help="家庭宽带网络仿真器 — RTMP推流卡顿率仿真与闭环措施评估")
console = Console()


def _load_params(config: Path | None) -> SimParams:
    """从 YAML 文件加载参数，若未指定则用默认值。"""
    if config is None:
        return DEFAULT_PARAMS.copy()
    import yaml
    with open(config, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return SimParams.from_dict(data)


@app.command()
def simulate(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="参数 YAML 配置文件路径"),
    measures_dir: Optional[Path] = typer.Option(None, "--measures-dir", "-m", help="额外措施 YAML 目录"),
    measures: Optional[str] = typer.Option(None, "--measures", help="要评估的措施名称，逗号分隔"),
    seed: Optional[int] = typer.Option(None, "--seed", "-s", help="随机种子"),
    duration: Optional[int] = typer.Option(None, "--duration", "-d", help="仿真时长 (秒)"),
    bitrate: Optional[float] = typer.Option(None, "--bitrate", "-b", help="RTMP推流码率 (Mbps)"),
    rssi: Optional[float] = typer.Option(None, "--rssi", help="WiFi RSSI (dBm)"),
    interference: Optional[float] = typer.Option(None, "--interference", help="WiFi 干扰占空比 (%)"),
    sta: Optional[int] = typer.Option(None, "--sta", help="STA 并发数量"),
    pon_up_load: Optional[float] = typer.Option(None, "--pon-up-load", help="PON口上行负载率 (%)"),
    uplink_bw: Optional[float] = typer.Option(None, "--uplink-bw", help="PON上行带宽 (Mbps)"),
    no_timeseries: bool = typer.Option(False, "--no-timeseries", help="不收集时序数据（加速）"),
):
    """运行RTMP推流仿真并输出结果。"""
    params = _load_params(config)

    # CLI 参数覆盖
    if seed is not None:
        params.random_seed = seed
    if duration is not None:
        params.sim_duration = duration
    if bitrate is not None:
        params.rtmp_bitrate = bitrate
    if rssi is not None:
        params.wifi_rssi = rssi
    if interference is not None:
        params.wifi_interference_ratio = interference
    if sta is not None:
        params.sta_count = sta
    if pon_up_load is not None:
        params.pon_up_load_ratio = pon_up_load
    if uplink_bw is not None:
        params.pon_uplink_bw = uplink_bw

    measure_names = [m.strip() for m in measures.split(",")] if measures else None

    engine = SimulationEngine(extra_measures_dir=measures_dir)

    with console.status("[bold green]正在仿真..."):
        report = engine.run_full(
            params,
            measure_names=measure_names,
            collect_timeseries=not no_timeseries,
        )

    # ── 参数概览 ──
    pt = Table(title="仿真参数", show_lines=True)
    pt.add_column("类别", style="cyan")
    pt.add_column("参数", style="white")
    pt.add_column("值", style="yellow")
    pt.add_row("WiFi", "信道/频宽/协议",
               f"CH{params.wifi_channel} / {params.wifi_bandwidth}MHz / {params.wifi_standard}")
    pt.add_row("WiFi", "RSSI / 底噪",
               f"{params.wifi_rssi} / {params.wifi_noise_floor} dBm")
    pt.add_row("WiFi", "干扰/重传/上行TCP重传",
               f"{params.wifi_interference_ratio}% / {params.wifi_retry_rate}% / {params.wifi_up_tcp_retrans_rate}%")
    pt.add_row("WiFi", "上行时延/抖动",
               f"{params.wifi_up_latency}ms / {params.wifi_up_jitter}ms")
    pt.add_row("PON", "上行/下行带宽",
               f"{params.pon_uplink_bw} / {params.pon_downlink_bw} Mbps")
    pt.add_row("PON", "上行负载/下行负载",
               f"{params.pon_up_load_ratio}% / {params.pon_down_load_ratio}%")
    pt.add_row("PON", "上行时延/抖动",
               f"{params.pon_up_latency}ms / {params.pon_up_jitter}ms")
    pt.add_row("RTMP", "推流码率/缓冲区",
               f"{params.rtmp_bitrate} Mbps / {params.rtmp_buffer_ms}ms")
    pt.add_row("RTMP", "帧间隔/仿真时长",
               f"{params.video_frame_interval}ms / {params.sim_duration}s")
    pt.add_row("RTMP", "总时间步数",
               f"{params.total_steps}")
    console.print(pt)

    # ── 基线结果 ──
    b = report.baseline_summary
    console.print(Panel(
        f"[bold red]RTMP卡顿率: {b.rtmp_stall_rate:.2f}%[/]\n"
        f"卡顿事件: {b.stall_count}次    平均时长: {b.avg_stall_duration_ms:.0f}ms\n"
        f"缓冲区耗尽: {b.buffer_empty_ratio:.1f}%    TCP阻塞: {b.tcp_block_ratio:.1f}%\n"
        f"平均上行吞吐: {b.avg_effective_throughput:.1f} Mbps    "
        f"带宽达标率: {b.bandwidth_meet_rate:.1f}%\n"
        f"瓶颈: {b.bottleneck}    断连次数: {b.reconnect_count}",
        title="基线结果 (无闭环措施)",
        border_style="red",
    ))

    # 卡顿类型分布
    if b.stall_type_distribution:
        dist = b.stall_type_distribution
        total = sum(dist.values()) or 1
        console.print(f"  卡顿类型分布: "
                      f"缓冲区耗尽={dist.get('buffer_empty',0)/total*100:.0f}% "
                      f"帧超时={dist.get('frame_timeout',0)/total*100:.0f}% "
                      f"TCP阻塞={dist.get('tcp_block',0)/total*100:.0f}% "
                      f"断连={dist.get('reconnect',0)/total*100:.0f}%")

    # ── 措施效果 ──
    if report.measure_results:
        rt = Table(title="闭环措施效果", show_lines=True)
        rt.add_column("措施", style="cyan", min_width=25)
        rt.add_column("卡顿率", style="yellow", justify="right")
        rt.add_column("带宽达标", justify="right")
        rt.add_column("改善幅度", justify="right")

        for mr in report.measure_results:
            imp_style = "green" if mr.improvement < 0 else "red"
            rt.add_row(
                f"{mr.description}\n({mr.measure_name})",
                f"{mr.summary.rtmp_stall_rate:.2f}%",
                f"{mr.summary.bandwidth_meet_rate:.1f}%",
                f"[{imp_style}]{mr.improvement:+.1f}%[/]",
            )

        if report.combined_result:
            cr = report.combined_result
            imp_style = "green" if cr.improvement < 0 else "red"
            rt.add_row(
                f"[bold]{cr.description}[/]",
                f"[bold]{cr.summary.rtmp_stall_rate:.2f}%[/]",
                f"[bold]{cr.summary.bandwidth_meet_rate:.1f}%[/]",
                f"[bold][{imp_style}]{cr.improvement:+.1f}%[/][/]",
            )

        console.print(rt)


@app.command()
def list_measures(
    measures_dir: Optional[Path] = typer.Option(None, "--measures-dir", "-m"),
):
    """列出所有可用的闭环措施。"""
    engine = SimulationEngine(extra_measures_dir=measures_dir)
    table = Table(title="可用闭环措施")
    table.add_column("名称", style="cyan")
    table.add_column("描述", style="white")
    for m in engine.registry.list_all():
        table.add_row(m.name, m.description)
    console.print(table)


if __name__ == "__main__":
    app()
