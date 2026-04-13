import ReactECharts from 'echarts-for-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { InsightRenderData } from '@/types/render';
import styles from './InsightDisplay.module.css';

interface Props {
  data: InsightRenderData;
}

function InsightDisplay({ data }: Props) {
  return (
    <div className={styles.container}>
      {data.charts.map((chart) => (
        <div key={chart.chartId} className={styles.chartCard}>
          <h3 className={styles.chartTitle}>{chart.title}</h3>
          <ReactECharts
            option={{
              ...chart.echartsOption,
              backgroundColor: 'transparent',
              textStyle: { color: '#9ca3af' },
              grid: { left: 50, right: 20, top: 30, bottom: 40 },
            }}
            style={{ height: 220, width: '100%' }}
            opts={{ renderer: 'svg' }}
            theme="dark"
          />
          {chart.conclusion?.trim() && (
            <div className={styles.chartConclusion}>{chart.conclusion}</div>
          )}
        </div>
      ))}

      {data.markdownReport?.trim() && (
        <div className={styles.reportWrap}>
          <div className={styles.report}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.markdownReport}</ReactMarkdown>
          </div>
        </div>
      )}
    </div>
  );
}

export default InsightDisplay;
