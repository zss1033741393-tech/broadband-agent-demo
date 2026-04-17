import { useSimulationStore } from '@/store/simulationStore';
import TimeSeriesChart from './TimeSeriesChart';
import styles from './SimulationView.module.css';

// RTMP bitrate threshold (Mbps) — matches _DEFAULT_PARAMS.rtmp_bitrate
const RTMP_BITRATE = 8.0;
// TCP retrans threshold (%) — matches _DEFAULT_PARAMS.tcp_retrans_threshold
const TCP_RETRANS_THRESHOLD = 5.0;

const PHASE_LABELS: Record<string, string> = {
  idle: '空闲',
  baseline: '基线段',
  fault: '故障注入',
  recovery: '故障自愈',
};

const PHASE_CSS: Record<string, string> = {
  idle: styles.phaseBadgeIdle,
  baseline: styles.phaseBadgeBaseline,
  fault: styles.phaseBadgeFault,
  recovery: styles.phaseBadgeRecovery,
};

function SimulationView() {
  const chartData = useSimulationStore((s) => s.chartData);
  const segments = useSimulationStore((s) => s.segments);
  const streaming = useSimulationStore((s) => s.streaming);
  const phase = useSimulationStore((s) => s.phase);
  const reset = useSimulationStore((s) => s.reset);

  const resetKey = useSimulationStore((s) => s.resetKey);
  const { step, throughput, buffer, stall, tcpRetrans, jitter, frameGen, frameDrop } = chartData;

  // frame_drop shown as negative bars (below zero) for visual separation
  const frameDrop_neg = frameDrop.map((v) => -v);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.headerTitle}>RTMP 推流仿真</span>
        <div className={styles.headerMeta}>
          {streaming && <div className={styles.streamingDot} title="流式进行中" />}
          <span className={`${styles.phaseBadge} ${PHASE_CSS[phase] ?? styles.phaseBadgeIdle}`}>
            {PHASE_LABELS[phase] ?? phase}
          </span>
          <button type="button" className={styles.resetBtn} onClick={reset}>
            重置
          </button>
        </div>
      </div>

      <div className={styles.charts}>
        {/* Chart 1 — 端到端上行带宽 */}
        <TimeSeriesChart
          key={`chart1-${resetKey}`}
          title="端到端上行带宽时序图"
          height={240}
          xData={step}
          series={[
            { name: '有效上行吞吐量(Mbps)', data: throughput, type: 'line', color: '#58a6ff' },
          ]}
          markLines={[{ value: RTMP_BITRATE, label: `码率 ${RTMP_BITRATE}M`, color: '#f85149' }]}
          segments={segments}
          streaming={streaming}
        />

        {/* Chart 2 — 缓冲区水位 */}
        <TimeSeriesChart
          key={`chart2-${resetKey}`}
          title="缓冲区水位时序图"
          height={200}
          xData={step}
          series={[
            { name: '缓冲区水位(B)', data: buffer, type: 'line', color: '#e67e22', areaStyle: true },
          ]}
          segments={segments}
          streaming={streaming}
        />

        {/* Chart 3 — 卡顿状态 */}
        <TimeSeriesChart
          key={`chart3-${resetKey}`}
          title="卡顿状态时序图"
          height={160}
          xData={step}
          series={[
            { name: '卡顿(0/1)', data: stall, type: 'bar', color: '#f85149' },
          ]}
          yAxes={[{ name: '', min: 0, max: 1 }]}
          segments={segments}
          streaming={streaming}
        />

        {/* Chart 4 — TCP重传率 + 时延抖动（双Y轴） */}
        <TimeSeriesChart
          key={`chart4-${resetKey}`}
          title="TCP重传率 / 时延抖动时序图"
          height={240}
          xData={step}
          series={[
            { name: 'TCP重传率(%)', data: tcpRetrans, type: 'line', color: '#a371f7' },
            { name: '上行抖动(ms)', data: jitter, type: 'line', color: '#39d353', yAxisIndex: 1 },
          ]}
          yAxes={[
            { name: 'TCP重传(%)', position: 'left' },
            { name: '抖动(ms)', position: 'right' },
          ]}
          markLines={[{ value: TCP_RETRANS_THRESHOLD, label: `阈值 ${TCP_RETRANS_THRESHOLD}%`, color: '#f85149' }]}
          segments={segments}
          streaming={streaming}
        />

        {/* Chart 5 — 帧生成 / 帧丢弃 */}
        <TimeSeriesChart
          key={`chart5-${resetKey}`}
          title="帧生成 / 帧丢弃时序图"
          height={160}
          xData={step}
          series={[
            { name: '帧生成', data: frameGen, type: 'bar', color: '#3fb950', stack: 'frame' },
            { name: '帧丢弃(负)', data: frameDrop_neg, type: 'bar', color: '#f85149', stack: 'frame' },
          ]}
          segments={segments}
          streaming={streaming}
        />
      </div>
    </div>
  );
}

export default SimulationView;
