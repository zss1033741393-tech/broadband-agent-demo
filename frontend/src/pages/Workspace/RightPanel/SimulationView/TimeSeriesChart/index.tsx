import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { ECharts, EChartsOption } from 'echarts';
import type { SimSegment } from '@/store/simulationStore';
import styles from './TimeSeriesChart.module.css';

const WINDOW_SIZE = 500; // visible points when streaming

export interface SeriesConfig {
  name: string;
  data: number[];
  type: 'line' | 'bar';
  color: string;
  areaStyle?: boolean;
  yAxisIndex?: number;
  stack?: string;
}

export interface MarkLineConfig {
  value: number;
  label: string;
  color?: string;
}

export interface YAxisConfig {
  name: string;
  min?: number;
  max?: number;
  position?: 'left' | 'right';
}

interface Props {
  title: string;
  height: number;
  xData: number[];
  series: SeriesConfig[];
  yAxes?: YAxisConfig[];
  markLines?: MarkLineConfig[];
  segments: SimSegment[];
  streaming: boolean;
}

function buildMarkArea(xData: number[], segments: SimSegment[]) {
  const nonBaseline = segments.filter((s) => s.type !== 'baseline');
  if (nonBaseline.length === 0) return undefined;
  return {
    silent: true,
    data: nonBaseline.map((seg) => [
      {
        xAxis: xData[Math.min(seg.startIdx, xData.length - 1)],
        itemStyle: {
          color:
            seg.type === 'fault'
              ? 'rgba(231, 76, 60, 0.15)'
              : 'rgba(46, 204, 113, 0.15)',
        },
      },
      { xAxis: xData[Math.min(seg.endIdx, xData.length - 1)] },
    ]),
  };
}

function buildOption(props: Props): EChartsOption {
  const { xData, series, yAxes, markLines, segments, streaming } = props;
  const total = xData.length;
  const windowStart = streaming && total > WINDOW_SIZE ? total - WINDOW_SIZE : 0;
  const windowEnd = total > 0 ? total - 1 : 0;

  const markArea = buildMarkArea(xData, segments);

  const yAxisConfig: EChartsOption['yAxis'] = (yAxes && yAxes.length > 0)
    ? yAxes.map((ya, i) => ({
        type: 'value' as const,
        name: ya.name,
        position: ya.position ?? (i === 0 ? 'left' : 'right'),
        min: ya.min,
        max: ya.max,
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { lineStyle: { color: '#21262d' } },
        axisLabel: { color: '#6b7280', fontSize: 11 },
        nameTextStyle: { color: '#6b7280', fontSize: 11 },
      }))
    : [{
        type: 'value' as const,
        axisLine: { lineStyle: { color: '#30363d' } },
        splitLine: { lineStyle: { color: '#21262d' } },
        axisLabel: { color: '#6b7280', fontSize: 11 },
      }];

  const seriesOptions: EChartsOption['series'] = series.map((s, idx) => {
    const ml = markLines && idx === 0
      ? {
          silent: true,
          data: markLines.map((cfg) => ({
            yAxis: cfg.value,
            lineStyle: { color: cfg.color ?? '#f85149', type: 'dashed' as const, width: 1 },
            label: {
              formatter: cfg.label,
              color: cfg.color ?? '#f85149',
              fontSize: 11,
              position: 'insideEndTop' as const,
            },
          })),
        }
      : undefined;

    const ma = markArea && idx === 0 ? markArea : undefined;

    const base = {
      name: s.name,
      type: s.type,
      data: s.data,
      yAxisIndex: s.yAxisIndex ?? 0,
      ...(ml && { markLine: ml }),
      ...(ma && { markArea: ma }),
    };

    if (s.type === 'line') {
      return {
        ...base,
        smooth: false,
        symbol: 'none',
        lineStyle: { color: s.color, width: 1.5 },
        itemStyle: { color: s.color },
        ...(s.areaStyle && {
          areaStyle: { color: s.color, opacity: 0.15 },
        }),
      };
    }
    return {
      ...base,
      barMaxWidth: 4,
      itemStyle: { color: s.color },
      ...(s.stack && { stack: s.stack }),
    };
  });

  return {
    backgroundColor: 'transparent',
    animation: false,
    grid: { left: 52, right: yAxes && yAxes.length > 1 ? 52 : 16, top: 28, bottom: streaming ? 20 : 40 },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { lineStyle: { color: '#30363d' } },
      axisLabel: {
        color: '#6b7280',
        fontSize: 10,
        interval: Math.floor(total / 6) || 0,
        formatter: (v: string) => String(Number(v)),
      },
      splitLine: { show: false },
    },
    yAxis: yAxisConfig,
    dataZoom: [
      {
        type: 'inside',
        startValue: windowStart,
        endValue: windowEnd,
        zoomOnMouseWheel: !streaming,
        moveOnMouseMove: !streaming,
      },
      ...(!streaming
        ? [
            {
              type: 'slider' as const,
              startValue: 0,
              endValue: windowEnd,
              height: 18,
              bottom: 4,
              borderColor: '#30363d',
              backgroundColor: '#0d1117',
              dataBackground: { lineStyle: { color: '#30363d' }, areaStyle: { color: '#21262d' } },
              fillerColor: 'rgba(22, 119, 255, 0.15)',
              handleStyle: { color: '#1677ff' },
              textStyle: { color: '#6b7280', fontSize: 10 },
            },
          ]
        : []),
    ],
    tooltip: {
      trigger: 'axis',
      backgroundColor: '#161b22',
      borderColor: '#30363d',
      textStyle: { color: '#c9d1d9', fontSize: 12 },
      axisPointer: { lineStyle: { color: '#30363d' } },
    },
    legend: {
      show: series.length > 1,
      top: 4,
      right: 8,
      textStyle: { color: '#8b949e', fontSize: 11 },
      itemHeight: 8,
    },
    series: seriesOptions,
  };
}

function TimeSeriesChart(props: Props) {
  const { title, height, xData, streaming } = props;
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);
  const prevLenRef = useRef(0);
  const prevStreamingRef = useRef(false);

  // Init chart on mount
  useEffect(() => {
    if (!containerRef.current) return;
    const chart = echarts.init(containerRef.current, 'dark', { renderer: 'canvas' });
    chartRef.current = chart;

    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  // Update chart when data or streaming state changes
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const lenChanged = xData.length !== prevLenRef.current;
    const streamingChanged = streaming !== prevStreamingRef.current;
    // Skip if nothing relevant changed and we already have data
    if (!lenChanged && !streamingChanged && prevLenRef.current > 0) return;

    // notMerge=true 仅在初始化时使用；streaming→false 只需 merge 更新 dataZoom/grid，
    // 无需重建 series，避免大数据量下的全量重绘卡顿
    const needsFullRebuild = prevLenRef.current === 0;
    chart.setOption(buildOption(props), needsFullRebuild);
    // Ensure canvas dimensions are correct (guards against 0-width init edge cases)
    chart.resize();
    prevLenRef.current = xData.length;
    prevStreamingRef.current = streaming;
  });

  return (
    <div className={styles.container}>
      <div className={styles.title}>{title}</div>
      <div ref={containerRef} style={{ height, width: '100%' }} />
    </div>
  );
}

export default TimeSeriesChart;
