"""RTMP直播实时卡顿判定模块（时间步级）。

4类卡顿：
1. 缓冲区耗尽卡顿 — buffer_empty_flag连续>=10步(50ms)
2. 帧传输超时卡顿 — frame_trans_latency>2×frame_interval 或 frame_drop，连续>=8步(40ms)
3. TCP重传阻塞卡顿 — tcp_block_flag连续>=20步(100ms)
4. 断连重推卡顿 — reconnect_flag=1，瞬时触发

严重程度优先级：断连重推 > 缓冲区耗尽 > TCP重传阻塞 > 帧传输超时
"""

from __future__ import annotations

# 持续阈值（时间步数）
T1_TH = 10   # 缓冲区耗尽：50ms / 5ms
T2_TH = 8    # 帧传输超时：40ms / 5ms
T3_TH = 20   # TCP重传阻塞：100ms / 5ms
T4_TH = 1    # 断连重推：瞬时触发

# 卡顿类型名称（按优先级降序）
STALL_TYPES = ["reconnect", "buffer_empty", "tcp_block", "frame_timeout"]


class RtmpStallDetector:
    """RTMP实时卡顿判定器。"""

    def detect(
        self,
        buffer_kpi: dict,
        rtmp_kpi: dict,
        trans_kpi: dict,
        params,
        prev_c1: int, prev_c2: int, prev_c3: int, prev_c4: int,
        prev_s1: int, prev_s2: int, prev_s3: int, prev_s4: int,
    ) -> dict:
        """在时间步n判定4类卡顿状态。

        Args:
            buffer_kpi: 缓冲区KPI (buffer_empty_flag, frame_drop_flag等)
            rtmp_kpi: RTMP层KPI (tcp_block_flag, reconnect_flag等)
            trans_kpi: 传输层KPI (frame_trans_latency等)
            params: SimParams
            prev_c1~c4: 上一步的持续计数器
            prev_s1~s4: 上一步的卡顿状态

        Returns:
            p1~p4: 前置条件 0/1
            c1~c4: 更新后的计数器
            s1~s4: 卡顿状态 0=无/1=持续/2=结束
            stall_active: 整体卡顿状态
            primary_stall_type: 主卡顿类型名称
        """
        # ── Step 1: 前置条件判定 ──
        # P1: 缓冲区溢出（帧丢弃）— 上行吞吐量持续低于码率，导致缓冲区满溢、帧被丢弃
        # frame_drop_flag=1 当 new_watermark > buffer_max，即码率持续超过上行带宽
        p1 = buffer_kpi["frame_drop_flag"]

        # P2: 帧传输超时 — 单帧传输时延 > 2×帧间隔（极低带宽下即使无溢出也会超时）
        p2 = (1 if trans_kpi["frame_trans_latency"] > params.video_frame_interval * 2
              else 0)

        p3 = rtmp_kpi["tcp_block_flag"]

        p4 = rtmp_kpi["reconnect_flag"]

        # ── Step 2: 计数器更新 ──
        c1 = (prev_c1 + 1) if p1 == 1 else 0
        c2 = (prev_c2 + 1) if p2 == 1 else 0
        c3 = (prev_c3 + 1) if p3 == 1 else 0
        c4 = (prev_c4 + 1) if p4 == 1 else 0  # 断连：实际不需累计

        # ── Step 3: 卡顿状态判定 ──
        s1 = self._judge_state(p1, c1, T1_TH, prev_s1)
        s2 = self._judge_state(p2, c2, T2_TH, prev_s2)
        s3 = self._judge_state(p3, c3, T3_TH, prev_s3)
        # 断连重推：瞬时触发
        if p4 == 1:
            s4 = 1
        elif prev_s4 == 1:
            s4 = 2  # 结束
        else:
            s4 = 0

        # ── Step 4: 整体卡顿判定 + 主类型提取 ──
        stall_active = any(s == 1 for s in [s1, s2, s3, s4])

        primary_stall_type = ""
        if stall_active:
            # 按优先级：断连>缓冲区耗尽>TCP阻塞>帧超时
            states = [s4, s1, s3, s2]
            for i, s in enumerate(states):
                if s == 1:
                    primary_stall_type = STALL_TYPES[i]
                    break

        return {
            "p1": p1, "p2": p2, "p3": p3, "p4": p4,
            "c1": c1, "c2": c2, "c3": c3, "c4": c4,
            "s1": s1, "s2": s2, "s3": s3, "s4": s4,
            "stall_active": stall_active,
            "primary_stall_type": primary_stall_type,
        }

    @staticmethod
    def _judge_state(p: int, c: int, threshold: int, prev_s: int) -> int:
        """判定单类卡顿状态。

        Returns:
            0: 无卡顿
            1: 卡顿持续
            2: 卡顿结束
        """
        if p == 1 and c >= threshold:
            return 1  # 卡顿持续
        elif p == 0 and prev_s == 1:
            return 2  # 卡顿结束
        else:
            return 0  # 无卡顿
