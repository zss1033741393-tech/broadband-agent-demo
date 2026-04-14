import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import ReactECharts from 'echarts-for-react';
import type { ChartItem } from '@/types/render';
import styles from './ReportView.module.css';

interface Props {
  content: string;
  charts: ChartItem[];
  onBack: () => void;
}

type Segment =
  | { kind: 'text'; content: string }
  | { kind: 'chart'; phaseId: number; stepId: number };

/** 解析 markdown 中的 [CHART:pXsY] 占位符，拆分为文字段落和图表段落 */
function parseSegments(markdown: string): Segment[] {
  const segments: Segment[] = [];
  const regex = /\[CHART:p(\d+)s(\d+)\]/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(markdown)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ kind: 'text', content: markdown.slice(lastIndex, match.index) });
    }
    segments.push({ kind: 'chart', phaseId: parseInt(match[1]), stepId: parseInt(match[2]) });
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < markdown.length) {
    segments.push({ kind: 'text', content: markdown.slice(lastIndex) });
  }

  return segments;
}

/** 为深色背景适配 ECharts option（覆盖颜色，不改变数据和布局） */
function darkifyOption(option: Record<string, unknown>): Record<string, unknown> {
  const title = option.title as Record<string, unknown> | undefined;
  const xAxis = option.xAxis as Record<string, unknown> | undefined;
  const yAxis = option.yAxis as Record<string, unknown> | undefined;
  const tooltip = option.tooltip as Record<string, unknown> | undefined;

  return {
    ...option,
    backgroundColor: 'transparent',
    textStyle: { color: '#9ca3af' },
    ...(title && {
      title: {
        ...title,
        textStyle: { ...(title.textStyle as object | undefined), color: '#e2e8f0' },
      },
    }),
    ...(xAxis && {
      xAxis: {
        ...xAxis,
        axisLabel: { ...(xAxis.axisLabel as object | undefined), color: '#9ca3af' },
        axisLine: { lineStyle: { color: '#374151' } },
        splitLine: { lineStyle: { color: '#1f2937' } },
      },
    }),
    ...(yAxis && {
      yAxis: {
        ...yAxis,
        axisLabel: { ...(yAxis.axisLabel as object | undefined), color: '#9ca3af' },
        nameTextStyle: { ...(yAxis.nameTextStyle as object | undefined), color: '#6b7280' },
        splitLine: { lineStyle: { color: '#1f2937' } },
      },
    }),
    ...(tooltip && {
      tooltip: {
        ...tooltip,
        backgroundColor: '#1e2738',
        borderColor: '#374151',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
      },
    }),
  };
}

function ChartCard({ chart }: { chart: ChartItem }) {
  return (
    <div className={styles.chartCard}>
      <ReactECharts
        option={darkifyOption(chart.echartsOption)}
        style={{ height: 300, width: '100%' }}
        opts={{ renderer: 'svg' }}
      />
      {chart.conclusion?.trim() && (
        <div className={styles.chartConclusion}>
          <span className={styles.conclusionIcon}>💡</span>
          {chart.conclusion}
        </div>
      )}
    </div>
  );
}

function ReportView({ content, charts, onBack }: Props) {
  // 构建 (phaseId-stepId) → ChartItem 索引
  const chartMap = new Map<string, ChartItem>();
  for (const c of charts) {
    chartMap.set(`${c.phaseId}-${c.stepId}`, c);
  }

  const segments = parseSegments(content);

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <span className={styles.title}>网络性能分析报告</span>
        <button className={styles.backBtn} onClick={onBack}>
          ‹ 返回地图
        </button>
      </div>
      <div className={styles.scroll}>
        <div className={styles.body}>
          {segments.map((seg, i) => {
            if (seg.kind === 'text') {
              return (
                <div key={i} className={styles.content}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{seg.content}</ReactMarkdown>
                </div>
              );
            }
            const chart = chartMap.get(`${seg.phaseId}-${seg.stepId}`);
            if (!chart) return null;
            return <ChartCard key={i} chart={chart} />;
          })}
        </div>
      </div>
    </div>
  );
}

export default ReportView;
